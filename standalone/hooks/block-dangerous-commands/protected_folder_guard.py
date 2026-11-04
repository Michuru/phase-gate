"""Protected-folder guard engine, shared by the PreToolUse hooks that import it (block-dangerous-commands.py).

It decides whether one Bash, PowerShell, Grep or Glob call would walk into a folder the owner has marked protected,
without naming it: `find /j` over a drive that holds the folder, `Get-ChildItem C:\\Users\\me -Recurse` over the
folder's parent, `rg x ~`, a wildcard such as `J:\\Pr*` that expands to the folder, a drive alias (`subst`, a junction)
that points at one of its ancestors. It also denies a command that names the folder at all (rule 0). Text matching
over the raw command, not a real shell parser: best-effort, same philosophy as the hook that calls it. The real
boundary would be an operating-system permission, which is a separate decision.

Config: protected-folders.json, `{"protected_folders": [<entry>, ...]}`. An entry is an absolute path string (the folder's
last name is rule 0, every ancestor up to the drive root is protected, the path must exist), or an object
`{"path": "<absolute path>", "tail": N, "optional": true}` (Design Docs/protected-folder-path-qualified-entries.md):
`tail` (default 1) is how many trailing path segments identify it in rule 0, so `work/companion` is matched in full and
the bare word `work` is left alone; an object entry's ancestors stop at its own parent; a relative path word that lands
inside it (from the cwd or after a `cd`) is denied; `optional` only means "do not raise when the path is missing" (the
text rules still apply). An unknown or duplicate key, a non-integer or out-of-range `tail` and a non-boolean `optional`
are config problems. Each existing path's 8.3 short spelling (COMPAN~1) is matched in every layer too.
  * `--config <file>` on the hook's command line names the one file to read; a named file that is missing or broken
    denies. This is how a user-level install should wire it, so the guard does not depend on the hook process
    inheriting any environment variable.
  * Without `--config` the default search reads `${CLAUDE_PROJECT_DIR}/.claude/protected-folders.json` and then
    `${CLAUDE_CONFIG_DIR or ~/.claude}/protected-folders.json` and unions the lists. A file that does not exist is
    skipped; a file that exists but is broken denies.
  * No file found, or an empty list: the guard is off (every function here allows).
Every way a config can be wrong (bad JSON, a duplicate key, an entry that is neither a string nor a valid object, a relative or
`~` path, a trailing separator, a bare drive or filesystem root, a glob or regex character in the path, a UNC path, a
required path that does not exist) is a deny
with a message naming the file, never a silent switch-off. The deny reaches every Grep and Glob call and every shell
statement that holds a recursion marker (find, rg, tree, ls -R, Get-ChildItem -Recurse, cp -r ...); Read and Edit
are not matched by the hooks, so the file can be fixed.

Python 3.9 or newer: no possessive quantifiers, no match statements, no X | Y annotations.
"""
import fnmatch
import json
import os
import posixpath
import re
import subprocess
import sys
from collections import namedtuple

IS_WINDOWS = os.name == "nt"
CONFIG_NAME = "protected-folders.json"

# A location: root is a lower-case drive ("j:") or "/" (a POSIX root); parts are the segments below it.
Loc = namedtuple("Loc", "root parts")
# One protected folder: display is the path as configured, segs its lower-case segments below root. tail is how many trailing
# segments rule 0 matches, optional that a missing path is no config problem, scoped that its ancestors stop at its own parent,
# spell the lower-case spellings of each segment (the long name plus its 8.3 short name; filled in by configure).
Folder = namedtuple("Folder", "display root segs tail optional scoped spell")
Folder.__new__.__defaults__ = (1, False, False, ())


class ConfigProblem(Exception):
    """A config file that cannot be trusted. The text names the file and says what is wrong."""


_BAD_PATH_CHARS = re.compile(r'[*?\[\]{}^$|+<>"]')
_DRIVE_PATH = re.compile(r"^([A-Za-z]):(?:[\\/](.*))?$", re.S)


def _canon_config_path(raw, tail=1, optional=False, scoped=False):
    """A configured path as a Folder, or raise ValueError with the reason it is not acceptable."""
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("an entry is not a non-empty string")
    p = raw.strip()
    if p.startswith("~"):
        raise ValueError("the path %r starts with ~ (write the full path)" % p)
    if _BAD_PATH_CHARS.search(p):
        raise ValueError("the path %r holds a glob or regex character (one of * ? [ ] { } ^ $ | + < > \")" % p)
    if p.startswith("\\\\") or p.startswith("//"):
        raise ValueError("the path %r is a UNC path (use a drive-letter path)" % p)
    m = _DRIVE_PATH.match(p)
    if m:
        root, rest = m.group(1).lower() + ":", m.group(2)
    else:
        m2 = re.match(r"^/mnt/([A-Za-z])(?:/(.*))?$", p, re.S)
        if m2:
            root, rest = m2.group(1).lower() + ":", m2.group(2)
        elif p.startswith("/"):
            root, rest = "/", p[1:]
        else:
            raise ValueError("the path %r is not absolute (write the drive letter or a leading /)" % p)
    if not rest or not rest.strip("\\/"):
        raise ValueError("the path %r is a bare drive or filesystem root (it would match everything)" % p)
    if re.search(r"[\\/]$", p):
        raise ValueError("the path %r ends with a separator (remove it)" % p)
    segs = [s for s in re.split(r"[\\/]+", rest) if s]
    if any(s in (".", "..") for s in segs):
        raise ValueError("the path %r holds a . or .. segment" % p)
    if not re.search(r"[A-Za-z0-9]", segs[-1]):
        raise ValueError("the folder name in %r has no letter or digit (the name rule would match that punctuation anywhere)" % p)
    if len(segs) < tail:
        raise ValueError("tail %d is more than the %d segments below the root of %r" % (tail, len(segs), p))
    return Folder(p, root, tuple(s.lower() for s in segs), tail, optional, scoped)


class _DuplicateKey(Exception):
    """A JSON object that holds the same key twice (json.load would silently keep the last one)."""


def _no_duplicate_keys(pairs):
    seen = set()
    for k, _ in pairs:
        if k in seen:
            raise _DuplicateKey(k)
        seen.add(k)
    return dict(pairs)


_ENTRY_KEYS = frozenset(("path", "tail", "optional"))


def _entry_folder(entry):
    """The Folder one config entry stands for (its path not yet checked against the disk): a string is the old form
    (tail 1, required, every ancestor protected); an object is {"path", "tail", "optional"} and is scoped."""
    if isinstance(entry, dict):
        extra = sorted(str(k) for k in entry if k not in _ENTRY_KEYS)
        if extra:
            raise ValueError("an entry has an unknown key %s (allowed: path, tail, optional)" % ", ".join(repr(k) for k in extra))
        if "path" not in entry:
            raise ValueError("an entry has no \"path\"")
        tail, optional = entry.get("tail", 1), entry.get("optional", False)
        if type(tail) is not int or tail < 1:
            raise ValueError("\"tail\" of %r must be a whole number from 1 up (not %r)" % (entry["path"], tail))
        if type(optional) is not bool:
            raise ValueError("\"optional\" of %r must be true or false (not %r)" % (entry["path"], optional))
        return _canon_config_path(entry["path"], tail, optional, True)
    if isinstance(entry, str):
        return _canon_config_path(entry)
    raise ValueError("an entry is neither a path string nor an object (%r)" % (entry,))


def _read_config_file(path, missing=None):
    """The Folder list one file holds; raise ConfigProblem naming the file when it cannot be trusted. An optional entry whose
    path is missing is accepted and its path appended to `missing` (when given)."""
    try:
        with open(path, encoding="utf-8-sig") as fh:
            data = json.load(fh, object_pairs_hook=_no_duplicate_keys)
    except FileNotFoundError:
        raise ConfigProblem("%s is missing" % path)
    except _DuplicateKey as e:
        raise ConfigProblem("%s holds the key %s twice (a duplicate would silently keep the last one)" % (path, e))
    except (OSError, UnicodeDecodeError) as e:
        raise ConfigProblem("%s cannot be read (%s)" % (path, e.__class__.__name__))
    except ValueError:
        raise ConfigProblem("%s is not valid JSON" % path)
    if not isinstance(data, dict) or not isinstance(data.get("protected_folders"), list):
        raise ConfigProblem('%s does not hold {"protected_folders": [ ... ]} (a list of paths or objects)' % path)
    out = []
    for entry in data["protected_folders"]:
        try:
            folder = _entry_folder(entry)
        except ValueError as e:
            raise ConfigProblem("%s: %s" % (path, e))
        if not os.path.exists(folder.display):
            if not folder.optional:
                raise ConfigProblem("%s: the path %r does not exist on disk" % (path, folder.display))
            if missing is not None:
                missing.append(folder.display)
        out.append(folder)
    return out


def config_files(argv, env):
    """(files to read, named) for this hook call: the --config file alone, or the default search. Raises
    ConfigProblem for a --config with no file after it."""
    argv = list(argv or [])
    for i, a in enumerate(argv):
        if a == "--config":
            if i + 1 >= len(argv) or not argv[i + 1].strip():
                raise ConfigProblem("--config on the hook command has no file after it")
            return [argv[i + 1]], True
        if a.startswith("--config="):
            if not a[9:].strip():
                raise ConfigProblem("--config= on the hook command has no file after it")
            return [a[9:]], True
    env = os.environ if env is None else env
    files = []
    project = env.get("CLAUDE_PROJECT_DIR")
    if project:
        files.append(os.path.join(project, ".claude", CONFIG_NAME))
    user_dir = env.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    files.append(os.path.join(user_dir, CONFIG_NAME))
    return files, False


def load_folders_ex(argv=None, env=None):
    """(folders, problem, missing_optional): load_folders plus the paths of optional entries that do not exist (for the health
    check). ([], None, []) means the guard is off."""
    missing = []
    try:
        files, named = config_files(argv, env)
        folders, seen = [], set()
        for f in files:
            key = os.path.normcase(os.path.abspath(f))
            if key in seen:
                continue
            seen.add(key)
            if not named and not os.path.isfile(f):
                continue
            folders.extend(_read_config_file(f, missing))
        return folders, None, missing
    except ConfigProblem as e:
        return [], str(e), []


def load_folders(argv=None, env=None):
    """(folders, problem): the protected folders for this call, or a ConfigProblem message when a config named or
    found cannot be trusted. ([], None) means the guard is off."""
    folders, problem, _ = load_folders_ex(argv, env)
    return folders, problem


# ---------------------------------------------------------------- state derived from the folders (see configure)

class _State(object):
    folders = ()
    root_any = None
    cwd_anc = None
    child_res = ()
    first_wild_res = ()
    name_re = None
    tail_re = None              # rule 0 for the path-qualified entries (tail above 1); None when there are none
    has_scoped = False
    inside_cache = {}           # (segment, tool, cwd) -> whether a word lands inside a scoped entry; reset by configure
    cwd_climb = None
    expanded = 0               # characters the variable expansions of the call being judged have added so far (see _EXPAND_CAP)


_S = _State()
_NOT_NAME = r"(?![\w$~*?\[{.\-])"
_NOT_NAME_MSYS = r"(?![\w$~*?\[{.\-:])"      # /c: in findstr /s /c:"x" is a switch value, not the drive
_END = r"[\\/]*(?![\\/])"
_HOME_VARS = (r"\$\{?(?:HOME|USERPROFILE)\}?|\$env:(?:HOME|USERPROFILE)|%(?:USERPROFILE|HOME)%"
              r"|\$\{?HOMEDRIVE\}?\$\{?HOMEPATH\}?|\$env:HOMEDRIVE\$env:HOMEPATH|%HOMEDRIVE%%HOMEPATH%")
_HOME_FORMS = r"(?:~|" + _HOME_VARS + ")"
_SEGCH = r"[^\\/\s'\"|;&)]"
_WILD_TOKEN = _SEGCH + r"*[*?\[{]" + _SEGCH + "*"          # one path segment that holds a wildcard character


def _home_loc():
    try:
        home = os.path.expanduser("~")
    except Exception:
        return None
    if not home or home == "~":
        return None
    loc = _norm_parts(home, None, "PowerShell" if IS_WINDOWS else "Bash")
    return loc if isinstance(loc, Loc) else None


def _alt(c):
    """Regex source for one path segment: a string is itself, a tuple is the alternatives (the long name and its 8.3 short name)."""
    if isinstance(c, str):
        return re.escape(c)
    return "(?:" + "|".join(re.escape(x) for x in c) + ")"


def _comp_alts(f):
    """The folder's segments as _forms and the child patterns want them: the configured spelling, or a tuple holding it and the
    other spellings (the 8.3 short name) the segment has."""
    out = []
    for i, comp in enumerate(_display_comps(f)):
        extra = [s for s in (f.spell[i] if i < len(f.spell) else ()) if s != comp.lower()]
        out.append((comp,) + tuple(extra) if extra else comp)
    return out


def _wants(f):
    """Per segment, the lower-case spellings that name it (the long name, plus the 8.3 short name when it has one)."""
    return f.spell if len(f.spell) == len(f.segs) else tuple((s,) for s in f.segs)


def _forms(root, comps, end):
    """Regex sources that name the directory root/comps in text. With end=True each ends as a complete token (the
    root-token check); with end=False it is a prefix that a path continues from."""
    esc = [_alt(c) for c in comps]
    tail = "".join(r"[\\/]+" + c for c in esc)
    stop = (_END + _NOT_NAME) if end else ""
    out = []
    if root == "/":
        if comps:
            out.append(r"(?<![\w.:/\\$\-~*])" + "".join("/+" + c for c in esc) + stop)
        elif not end:
            out.append(r"(?<![\w.:/\\$\-~*])(?=/)")
        else:
            out.append(r"(?<=['\"])/(?=['\"])")           # a quoted lone slash ('/' in os.walk('/')), never a division
        return out
    letter = re.escape(root[0])
    # the device prefix (\\?\ and \\.\) in either slash style, then the drive
    out.append(r"(?<![\w$])[\\/]{2}[?.][\\/]" + letter + ":" + tail + stop)
    # a plain drive: not /c: (a findstr or cmd switch value, so one slash before it is no drive), but file:///J:/ is one
    out.append(r"(?<![\w$])(?:(?<!/)|(?<=//))" + letter + ":" + tail + stop)
    out.append(r"(?<![\w$])[\\/]{2}(?:[?.][\\/]unc[\\/])?[^\\/\s]+[\\/]" + letter + r"\$" + tail + stop)
    out.append(r"(?<![\w.:/\\$\-~*])/(?:mnt/|(?:proc/)?cygdrive/)?" + letter + tail
               + ((r"/*(?!/)" + _NOT_NAME_MSYS) if end else ""))
    return out


_NEVER = re.compile(r"(?!x)x")                 # matches nothing (an empty alternation would match everything)


def _name_words(name):
    """One path segment as a rule-0 pattern. Between two words of the name: space, _ and -, plus the characters a shell puts around
    an escaped or quoted space (a backslash in Git Bash, a backtick in PowerShell, a caret in cmd, a quote pair in any of them), so
    'Keep\\ Out\\ Zone' still matches."""
    if not re.search(r"[A-Za-z0-9]", name):
        return re.escape(name)
    return r"[\s_\-\\`^'\"]*".join(re.escape(w) for w in re.split(r"[\s_\-]+", name) if w)


def _short_form(path):
    """The 8.3 short spelling of an existing path ("C:\\Users\\PARTNE~1\\x"), or "" when there is none or it cannot be read.
    Windows only; a failure of any kind means "no short form". Tests replace this function."""
    if not IS_WINDOWS:
        return ""
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetShortPathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
        k32.GetShortPathNameW.restype = wintypes.DWORD
        size = 1024
        buf = ctypes.create_unicode_buffer(size)
        n = k32.GetShortPathNameW(path, buf, size)
        if n == 0 or n >= size:
            return ""
        return buf.value
    except Exception:
        return ""


def _with_spellings(f):
    """The folder with its per-segment spellings filled in: the lower-case segment, plus its 8.3 short name when the volume made
    one. A path that does not exist (a missing optional entry) has none."""
    comps = _display_comps(f)
    spell = [[s] for s in f.segs]
    if len(comps) == len(f.segs):
        drive = f.root != "/"
        path = (f.root[0].upper() + ":\\" + "\\".join(comps)) if drive else ("/" + "/".join(comps))
        try:
            short = _short_form(path) if os.path.exists(f.display) else ""
        except Exception:
            short = ""
        parts = [p for p in re.split(r"[\\/]+", short) if p] if short else []
        if drive and parts:
            parts = parts[1:]                                # the drive letter
        if len(parts) == len(comps):                         # one segment for each of the folder's
            for i, p in enumerate(parts):
                if p.lower() != f.segs[i] and p.lower() not in spell[i]:
                    spell[i].append(p.lower())
    return f._replace(spell=tuple(tuple(s) for s in spell))


def _name_hit(text):
    """Rule 0: does the text name a protected folder (a last name, or a path-qualified tail)? A tail is also read with quotes
    removed and ./ and seg/../ folded, the way the shell resolves them."""
    if _S.name_re.search(text):
        return True
    if _S.tail_re is None:
        return False
    return bool(_S.tail_re.search(text) or _S.tail_re.search(_clean_for_0c(text)))


def configure(folders):
    """Compile the text patterns for these folders. Called once per hook call (and per test)."""
    folders = [_with_spellings(f) for f in folders]
    _S.folders = tuple(folders)
    _S.has_scoped = any(f.scoped for f in folders)
    _S.inside_cache = {}
    home = _home_loc()
    anc_tokens, cwd_tokens, child = [], [], []
    for f in folders:
        alts = _comp_alts(f)
        # every proper ancestor, the root first; a scoped entry (an object entry) has only its own parent
        for k in (range(len(f.segs)) if not f.scoped else [len(f.segs) - 1]):
            anc_tokens.extend(_forms(f.root, alts[:k], True))
            cwd_tokens.extend(_forms(f.root, alts[:k], False))
        child.append((f, 0, _forms(f.root, [], False)))
        if home and home.root == f.root and len(home.parts) < len(f.segs) \
                and tuple(p.lower() for p in home.parts) == f.segs[:len(home.parts)]:
            hk = len(home.parts)                          # the home directory is on the way to the folder
            comps = alts[hk:]
            for k in (range(len(f.segs) - hk) if not f.scoped else [len(f.segs) - hk - 1]):
                tail = "".join(r"[\\/]+" + _alt(c) for c in comps[:k])
                anc_tokens.append(r"(?<![\w$])" + _HOME_FORMS + tail + _END + _NOT_NAME)
            child.append((f, hk, [r"(?<![\w$])" + _HOME_FORMS]))
    _S.root_any = re.compile("|".join(anc_tokens), re.IGNORECASE) if anc_tokens else None
    _S.cwd_anc = re.compile("^(?:" + "|".join(cwd_tokens) + r")[\\/]*$", re.IGNORECASE) if cwd_tokens else None
    res, first_wild = [], []
    for f, offset, prefixes in child:
        comps = _comp_alts(f)[offset:]
        for pre in prefixes:
            levels = "".join(r"[\\/]+(?:%s|%s)" % (_alt(c), _WILD_TOKEN) for c in comps)
            res.append((re.compile("(?:" + pre + ")(" + levels + r")(?=[\\/\s'\"|;&)]|$)", re.IGNORECASE), f, offset))
            first_wild.append(re.compile("(?:" + pre + r")[\\/]+(" + _WILD_TOKEN + ")", re.IGNORECASE))
    _S.child_res = tuple(res)
    _S.first_wild_res = tuple(first_wild)
    words, tails = [], []
    for f in folders:
        alts = _comp_alts(f)
        if f.tail <= 1:                      # the folder's last name, as ever (its 8.3 short name too)
            last = alts[-1]
            for name in ((last,) if isinstance(last, str) else last):
                words.append(r"(?<![A-Za-z0-9])" + _name_words(name) + r"(?![A-Za-z0-9])"
                             if re.search(r"[A-Za-z0-9]", name) else re.escape(name))
        else:                                # its last `tail` segments in full: the bare last name alone is not enough
            joined = r"\.*[\\/]+".join("(?:" + "|".join(_name_words(n) for n in ((c,) if isinstance(c, str) else c)) + ")"
                                    for c in alts[-f.tail:])
            tails.append(r"(?<![A-Za-z0-9])" + joined + r"(?![A-Za-z0-9])")
    _S.name_re = re.compile("|".join(words), re.IGNORECASE) if words else _NEVER
    _S.tail_re = re.compile("|".join(tails), re.IGNORECASE) if tails else None
    drives = sorted({f.root for f in folders if f.root != "/" and not f.scoped})
    climb = []
    for d in drives:
        L = "[" + re.escape(d[0]) + re.escape(d[0]).upper() + "]"
        climb.append(L + ":|/" + L + "|/mnt/" + L)
    _S.cwd_climb = re.compile(r"^(?:" + "|".join(climb) + r")[\\/]") if climb else None


def _display_comps(f):
    """The folder's segments with their configured spelling (the lower-cased copy is in f.segs)."""
    m = _DRIVE_PATH.match(f.display)
    if m:
        rest = m.group(2) or ""
    else:
        m2 = re.match(r"^/mnt/[A-Za-z](?:/(.*))?$", f.display, re.S)
        rest = (m2.group(1) or "") if m2 else f.display[1:]
    return [s for s in re.split(r"[\\/]+", rest) if s]


# ---------------------------------------------------------------- the engine
class _RootAny(object):
    """A text token that names a directory above a protected folder (its drive root and every ancestor): J:, J:\\,
    \\\\?\\J:\\, /j, /mnt/j, /cygdrive/j, \\\\host\\J$, and for a deeper ancestor its path in either slash style."""

    def search(self, text):
        return _S.root_any.search(text) if _S.root_any else None


ROOT_ANY = _RootAny()
_ENCODED = re.compile(
    r"(?i)(?<![\w-])(?:powershell|pwsh)(?:\.exe)?\b[^\n;|&]*?\s[-/](?:e|ec|en\w*)\s+['\"]?[A-Za-z0-9+/=]{16,}")
_ALIAS_VERBS = re.compile(
    r"(?i)(?<![\w-])subst(?:\.exe)?\s|\bNew-PSDrive\b[^\n]*-Root\b|(?<![\w-])net(?:\.exe)?\s+use\b"
    r"|\bmklink\b|\bNew-Item\b[^\n]*-ItemType\s+(?:Junction|SymbolicLink)\b")
_EMBEDDED = re.compile(
    r"\bos\.walk\b|\bos\.fwalk\b|(?<!\bast)\.walk\s*\(|\bRecurseSubdirectories\b|\brglob\b|\bi?glob\s*\([^)]*\*\*|\breaddir(?:Sync)?\b[^)]*recursive"
    r"|\bglobSync\b|\bfs\.glob\b|\bAllDirectories\b|\bwalk_files\b|\bshutil\.(?:copytree|make_archive)\b"
    # .NET: the integer 1 is SearchOption.AllDirectories, and PowerShell reads the method names without regard to case
    r"|(?i:\b(?:Get|Enumerate)(?:Files|Directories|FileSystemEntries|FileSystemInfos)\s*\([^)]*,\s*"
    r"(?:1|[\[\w.]*SearchOption\]?::AllDirectories)\s*\))")
_WILD_AFTER_SEP = re.compile(r"(?<=[\\/])[*?]+")


def _embedded_root(text):
    """An embedded recursive call (os.walk, glob(..., recursive=True), GetFiles(..., 1) ...) in a text that names a directory
    above a protected folder. The root is also read with a wildcard run directly after its separator turned into a space, so
    glob.glob('J:/**', recursive=True) (the `**` after `J:/` keeps it from being a whole root token) is seen as the root."""
    if not _EMBEDDED.search(text):
        return False
    return bool(ROOT_ANY.search(text) or ROOT_ANY.search(_WILD_AFTER_SEP.sub(" ", text)))
_SHELLOUT = re.compile(
    r"(?i)\b(?:os\.system|os\.popen|subprocess\.\w+|execSync|spawnSync|child_process|popen|system|exec)\s*\(")
_LEADERS = re.compile(
    r"^\s*(?:(?:do|then|else|elif|if|while|until|time|source|!|\.)\s+|[A-Za-z_]\w*=(?:\"[^\"]*\"|'[^']*'|\S*)\s+)+",
    re.IGNORECASE)
_INTERP_ANY = re.compile(
    r"(?<![\w.\-])(?:python3?|py|pythonw|node|nodejs|perl|ruby|pwsh|powershell|bash|sh|cmd|wsl|iex|invoke-expression|eval)"
    r"(?:\.exe)?\b", re.IGNORECASE)               # not inside a file name: tool.py is not the interpreter py
_TEXT_SINK = re.compile(           # a redirection into a FILE (not 2>$null or 2>&1) counts as a text sink
    r"(?i)\bgit\s+(?:commit|tag|notes|stash)\b|\bcat\b|(?<![\d&>])>>?(?!&)\s*[^\s&$]|\btee\b|\bSet-Content\b"
    r"|\bAdd-Content\b|\bOut-File\b")
_HEREDOC_RE = re.compile(r"<<-?[ \t]*(['\"]?)(\w+)\1([^\n]*)\n(.*?)\n[ \t]*\2[ \t]*(?:\n|$)", re.S)
_HERESTR_RE = re.compile(r"@(['\"])[ \t]*\n(.*?)\n\1@", re.S)
_CD_WORDS = frozenset(("cd", "chdir", "set-location", "sl", "pushd", "push-location", "popd", "pop-location"))
_LISTERS = frozenset(("ls", "dir", "gci", "get-childitem"))
_ALWAYS_RECURSIVE = frozenset((
    "find", "rg", "fd", "fdfind", "tree", "du", "robocopy", "xcopy", "tar", "7z", "7za", "compress-archive",
    "ag", "ack", "rsync", "zip", "ncdu", "locate"))
_GREPS = frozenset(("grep", "egrep", "fgrep", "rg", "findstr", "ripgrep"))
_PREFIX_WORDS = frozenset((
    "sudo", "time", "nice", "nohup", "env", "command", "xargs", "start", "call", "wsl", "powershell", "pwsh", "cmd",
    "timeout", "stdbuf", "ionice", "setsid", "chrt", "taskset", "unbuffer", "doas", "exec", "builtin", "busybox",
    "watch", "start-process", "parallel"))
_WRAPPERS = frozenset((
    "powershell", "pwsh", "bash", "sh", "cmd", "wsl", "env", "start", "start-process", "invoke-expression", "iex",
    "invoke-command", "eval", "python", "python3", "py", "pythonw", "node", "nodejs", "perl", "ruby"))
_QUIET = frozenset(("git", "gh", "echo", "printf", "write-output", "write-host"))
_PRINTERS = frozenset((
    "echo", "printf", "write-output", "write-host",
    # pipeline filters: their quoted arguments are comparison values (-like 'J:\*'), not paths they open. NOT where
    # (where.exe /r is a recursive search) and NOT select-string/sls (-Path 'J:\P*\*.txt' opens files).
    "where-object", "foreach-object", "select-object", "select", "sort-object", "sort",
    "format-table", "format-list", "ft", "fl", "out-file", "out-string", "out-host", "convertto-json",
    "measure-object", "group-object", "tee-object", "compare-object"))
_FEEDS = frozenset((      # commands that take a root handed to them through a pipe
    "xargs", "parallel", "get-childitem", "gci", "ls", "dir", "get-item", "get-content", "resolve-path", "cat", "find"))
# Places a command can start: the start, a bracket, | ; &, $( , a ) that is followed by something (a case arm), an
# assignment (= += -= *= /=, spaced or glued to a $variable), the word `in` (foreach ($f in gci ...)), and find's -exec.
_CMD_POS = re.compile(
    r"(?:^|[(\{|;&]|\$\(|\)(?=\s*\S)|(?<=\s)(?:[+\-*/]?=(?!=)|in(?=\s)|-(?:exec|execdir|ok|okdir)(?=\s))"
    r"|\$[\w:]+[+\-*/]?=)\s*(?:&\s*)?(?:['\"]([^'\"]+)['\"]|([\w.\-\\/:]+))")
_TOOL_CTX = ["Bash"]          # the tool whose text is being scanned: decides the escape character


def _esc():
    return "`" if _TOOL_CTX[0] == "PowerShell" else "\\"


def _strip_leaders(seg):
    """Drop shell keywords (do, then, if, while, !, ., time) and NAME=value environment prefixes from the front of a
    command, so `MSYS_NO_PATHCONV=1 find /j` and `do find /j` are read as the find they are."""
    return _LEADERS.sub("", seg, count=1)


def _expand_braces(s, limit=64):
    """Brace-expand s. Returns (expansions, truncated); stops once the cap is reached so a pile of {a,b} groups
    cannot stall the hook, and the caller treats a truncated expansion as a hit."""
    out, queue = [], [s]
    while queue:
        if len(out) >= limit or len(queue) > 4 * limit:
            return out, True
        cur = queue.pop()
        m = re.search(r"\{([^{}]*)\}", cur)
        if not m:
            out.append(cur)
            continue
        for alt in m.group(1).split(","):
            queue.append(cur[:m.start()] + alt + cur[m.end():])
    return out, False


_WILD = re.compile(r"[*?\[{]")


def _seg_match(want, seg):
    """(matches, by_wildcard): does the typed segment `seg` name the protected segment `want` (lower case), exactly
    or by a wildcard, case-insensitively? A brace expansion too big to finish counts as a match: nobody needs that
    next to a protected folder."""
    wants = (want,) if isinstance(want, str) else want         # one lower-case name, or the spellings of one segment
    low = seg.lower()
    if low in wants:
        return True, False
    if not _WILD.search(seg):
        return False, False
    expansions, truncated = _expand_braces(low)
    if truncated or any(fnmatch.fnmatchcase(w, e) for w in wants for e in expansions):
        return True, True
    return False, False


def _covers_by_glob(root, segs, scoped_only=False):
    """True when the typed segments, from `root`, reach a protected folder through at least one wildcard (J:\\Pr*,
    C:\\Us*\\me\\sec*): every segment up to the folder's depth matches and one of them is a wildcard. The exact
    spelling is rule 0's. scoped_only: look at the object entries only (the containment check, which must not add denies
    for a string entry)."""
    for f in _S.folders:
        if f.root != root or len(segs) < len(f.segs) or (scoped_only and not f.scoped):
            continue
        wild = False
        for want, seg in zip(_wants(f), segs):
            ok, by_wild = _seg_match(want, seg)
            if not ok:
                break
            wild = wild or by_wild
        else:
            if wild:
                return True
    return False


def _is_ancestor(loc):
    """True when the location is a directory above a protected folder (its drive root, J:\\, included), so a
    recursive search that starts there walks into it. Wildcard segments count where they could match. A scoped (object) entry
    has only one ancestor, its own parent."""
    if not isinstance(loc, Loc):
        return False
    for f in _S.folders:
        if f.root != loc.root:
            continue
        depth_ok = len(loc.parts) == len(f.segs) - 1 if f.scoped else len(loc.parts) < len(f.segs)
        if depth_ok and all(_seg_match(want, seg)[0] for want, seg in zip(_wants(f), loc.parts)):
            return True
    return False


def _inside(loc):
    """True when the location is inside a scoped (object) entry: its full path, or anything below it, spelled out (the long
    name or the 8.3 short one, any case; a wildcard segment is not read as a match here, the wildcard rules do that)."""
    if not isinstance(loc, Loc) or not _S.has_scoped:
        return False
    for f in _S.folders:
        if f.scoped and f.root == loc.root and len(loc.parts) >= len(f.segs) \
                and all(seg.lower().rstrip(". ") in want for want, seg in zip(_wants(f), loc.parts)):     # Windows drops a trailing dot or space
            return True
    return False


def _is_rooted(loc):
    """A location a recursion marker should be judged against: an ancestor of a protected folder, or a wildcard
    last segment under one (J:\\*.pdf with a recursion flag walks every folder of the drive)."""
    if not isinstance(loc, Loc):
        return False
    if _is_ancestor(loc):
        return True
    return bool(loc.parts and re.search(r"[*?\[]", loc.parts[-1]) and _is_ancestor(Loc(loc.root, loc.parts[:-1])))


def _resolve(rest, base):
    parts = list(base)
    for seg in re.split(r"[\\/]+", rest):
        if seg in ("", "."):
            continue
        if seg == "..":
            if parts:
                parts.pop()
        else:
            parts.append(seg)
    return parts


_HOME_PREFIX = re.compile(r"^(?:~|" + _HOME_VARS + r")(?=[\\/]|$)", re.IGNORECASE)
_HOME_DRIVE = re.compile(r"^(?:\$env:HOMEDRIVE|%HOMEDRIVE%|\$\{?HOMEDRIVE\}?)(?=[\\/]|$)", re.IGNORECASE)
_USER_HOME = re.compile(r"^~([A-Za-z0-9_.\-]+)(?=[\\/]|$)")          # ~name: another user's home, a sibling of this one


def _is_homeish(t):
    return bool(_HOME_PREFIX.match(t) or _USER_HOME.match(t) or _HOME_DRIVE.match(t))


def _norm_variants(path, cwd, tool):
    """Every reading of a path that could be right. Almost always one. A path that starts with ~ has two: the real home
    directory (Bash, PowerShell cmdlets), and a literal `~` folder under the current directory, which is how cmd.exe and
    Windows PowerShell 5.1 hand `~` to a native program, so a `..` climb counts from the cwd there."""
    out = [_norm_parts(path, cwd, tool)]
    p = path.strip().strip("'\"")
    if IS_WINDOWS and tool != "Bash" and _is_homeish(p):
        # The Bash reading, kept as a conservative over-deny. PowerShell and cmd pass the expanded home to a native program
        # as C:\Users\me, and Git's MSYS tools clamp a .. climb at C:\ (they do not reach the MSYS root), so from these tools
        # ~/../../../j resolves to C:\j, not to J:. Under Git Bash itself the home is /c/Users/me and the climb does pass the
        # drive letter, so that reading is real there; applying it to the other tools costs only a few denied climbs.
        out.append(_norm_parts(path, cwd, "Bash"))
    if (p == "~" or p.startswith(("~/", "~\\"))) and isinstance(cwd, Loc):
        out.append(Loc(cwd.root, tuple(_resolve(p, cwd.parts))))
    return out


def _riskiest(locs):
    """The reading that sits at or above a protected folder if there is one, else the first."""
    for loc in locs:
        if _is_rooted(loc):
            return loc
    return locs[0]


def _norm_parts(path, cwd, tool):
    """A Loc (a drive or POSIX root plus the segments below it; no segments is the root itself); False when the
    path is somewhere no protected folder can be (an MSYS-root path under Git Bash); None when it cannot be known
    (a variable, or a relative path from an unknown directory). `cwd` is the Loc the path is relative to, or
    None/False."""
    p = path.strip().strip("'\"")
    if not p:
        return None
    p = re.sub(r"^/(?:proc/)?cygdrive/", "/", p)                 # Git Bash's other names for the drive mounts
    p = re.sub(r"^[\\/]{2}\?[\\/]UNC[\\/]", r"\\\\", p, flags=re.IGNORECASE)
    hd = _HOME_DRIVE.match(p)
    if hd and not _HOME_PREFIX.match(p):                         # $env:HOMEDRIVE / %HOMEDRIVE% on its own: the home's drive root
        home = _home_loc()
        if home is None or home.root == "/":
            return None
        return Loc(home.root, tuple(_resolve(p[hd.end():], ())))
    own = _HOME_PREFIX.match(p)
    other = None if own else _USER_HOME.match(p)
    hm = own or other
    if hm:                                                       # the real home directory (HOME / USERPROFILE), or ~name
        home = _home_loc()
        if home is None:
            return None
        base = home
        if other:                                                # ~name: guessed as a sibling of this user's home directory
            if not home.parts:
                return None
            base = Loc(home.root, home.parts[:-1] + (other.group(1),))
        if IS_WINDOWS and tool == "Bash" and base.root != "/":
            # under Git Bash the home directory is /c/Users/me, and climbing out of it with .. passes the drive letter
            # and reaches the MSYS root, where /j is the J: drive again (~/../../../j)
            p = "/" + base.root[0] + "".join("/" + s for s in base.parts) + p[hm.end():].replace("\\", "/")
        else:
            return Loc(base.root, tuple(_resolve(p[hm.end():], base.parts)))
    if p.startswith("/") and not p.startswith("//"):
        p = posixpath.normpath(p)              # Git Bash resolves /c/../j to /j, so do the same before reading the drive
    m = re.match(r"^[\\/]{2}[^\\/]+[\\/]([A-Za-z])\$(.*)$", p)
    if m:
        return Loc(m.group(1).lower() + ":", tuple(_resolve(m.group(2), ())))
    if re.search(r"[$%`]", p):
        return None
    m = re.match(r"^(?:[\\/]{2}[?.][\\/])?([A-Za-z]):(.*)$", p)
    if m:
        return Loc(m.group(1).lower() + ":", tuple(_resolve(m.group(2), ())))
    m = re.match(r"^/mnt/([A-Za-z])(?:/(.*))?$", p) or (IS_WINDOWS and re.match(r"^/([A-Za-z])(?:/(.*))?$", p))
    if m:
        return Loc(m.group(1).lower() + ":", tuple(_resolve(m.group(2) or "", ())))
    if p[0] in "\\/":
        if IS_WINDOWS:                         # a bare root path means the drive of the current directory (not under Git Bash)
            return Loc(cwd.root, tuple(_resolve(p, ()))) if (tool != "Bash" and isinstance(cwd, Loc)) else False
        if p[0] == "/":
            return Loc("/", tuple(_resolve(p, ())))
    if not isinstance(cwd, Loc):
        return cwd
    return Loc(cwd.root, tuple(_resolve(p, cwd.parts)))


def _tokens(seg):
    """Words of a segment, quotes stripped, redirections (2>/dev/null, 2>&1) and null sinks dropped."""
    toks = [t.strip("'\"") for t in re.findall(r"\"[^\"]*\"|'[^']*'|\S+", seg)]
    return [t for t in toks if not re.fullmatch(r"\d*[<>]{1,2}(?:&\d|\S*)", t) and t not in ("/dev/null", "$null", "NUL")]


def _split_top(text, mode):
    """Split on statement separators (mode 'stmt': ; newline && ||) or a single pipe (mode 'pipe'), outside quotes
    and outside any bracket pair, so a script block stays inside its pipeline."""
    parts, buf, depth, q, i, n = [], [], 0, None, 0, len(text)
    esc = _esc()
    while i < n:
        c = text[i]
        # an escaped quote (it\'s, "a`"b") does not open or close a string; J:\ is a drive root, not an escape, but a
        # doubled escape ("J:\\") is always a pair
        if c == esc and q != "'" and i + 1 < n and (text[i - 1:i] != ":" or text[i + 1] == esc):
            buf.append(c)
            buf.append(text[i + 1])
            i += 2
            continue
        if q:
            buf.append(c)
            if c == q:
                q = None
            i += 1
            continue
        if c in "'\"":
            q = c
            buf.append(c)
            i += 1
            continue
        if c in "({[":
            depth += 1
        elif c in ")}]":
            depth = max(0, depth - 1)
        if depth == 0:
            if mode == "stmt":
                if text[i:i + 2] in ("&&", "||"):
                    parts.append("".join(buf))
                    buf = []
                    i += 2
                    continue
                if c in ";\n" or (c == "&" and "".join(buf).strip()          # a lone & (background) also starts a new command
                                  and text[i - 1:i] not in (">", "&") and text[i + 1:i + 2] not in (">", "&")
                                  and not text[i + 1:i + 2].isdigit()):
                    parts.append("".join(buf))
                    buf = []
                    i += 1
                    continue
            elif c == "|" and text[i + 1:i + 2] != "|" and text[i - 1:i] != "|":
                parts.append("".join(buf))
                buf = []
                i += 1
                continue
        buf.append(c)
        i += 1
    parts.append("".join(buf))
    return parts


def _groups(s):
    """Contents of the top-level (...) and {...} groups of a statement. Brackets inside a quoted string are text, not a
    subshell, except a $( ) inside double quotes, which does run."""
    out, depth, start, q, skip, esc = [], 0, 0, None, False, _esc()
    for i, c in enumerate(s):
        if skip:
            skip = False
            continue
        if c == esc and q != "'" and (s[i - 1:i] != ":" or s[i + 1:i + 2] == esc):
            skip = True
            continue
        if depth == 0:
            if q:
                if c == q:
                    q = None
                elif q == '"' and c == "(" and s[i - 1:i] == "$":
                    start, depth = i + 1, 1
                continue
            if c in "'\"":
                q = c
                continue
        if c in "({":
            if depth == 0:
                start = i + 1
            depth += 1
        elif c in ")}" and depth:
            depth -= 1
            if depth == 0:
                out.append(s[start:i])
    return out


def _join_continuations(t):
    if _TOOL_CTX[0] == "PowerShell":                 # a backtick before a newline continues the line in PowerShell only
        t = re.sub(r"`[ \t]*\r?\n[ \t]*", " ", t)
    t = re.sub(r"(?<=\s)\\[ \t]*\r?\n[ \t]*", " ", t)
    return re.sub(r"\|[ \t]*\r?\n[ \t]*", "| ", t)


def _sub_bodies(regex, text, body_group, owner_of, bodies):
    def repl(m):
        owner = owner_of(m)
        if _INTERP_ANY.search(owner) or not _TEXT_SINK.search(owner):
            bodies.append(m.group(body_group))     # fed to an interpreter or shell, or not clearly text: scan it
        return "\n"
    return regex.sub(repl, text)


def _strip_bodies(text):
    """Remove heredoc and here-string bodies that are plain text (a commit message, a note); return the rest plus
    the bodies worth scanning (those fed to an interpreter or shell, or whose owner is not clearly a text sink)."""
    bodies = []

    def heredoc_owner(m):
        line_start = text.rfind("\n", 0, m.start()) + 1
        return re.split(r"&&|\|\||[;|]", text[line_start:m.start()])[-1] + m.group(3)

    clean = _sub_bodies(_HEREDOC_RE, text, 4, heredoc_owner, bodies)
    text2 = clean

    def herestr_owner(m):
        # the command that owns a here-string can sit before it (python -c @") or after it (@'...'@ | Set-Content x)
        line_start = text2.rfind("\n", 0, m.start()) + 1
        line_end = text2.find("\n", m.end())
        return text2[line_start:m.start()] + " " + text2[m.end():line_end if line_end != -1 else len(text2)]

    clean = _sub_bodies(_HERESTR_RE, text2, 2, herestr_owner, bodies)
    return clean, bodies


def _args_end(rest):
    """The argument text of a command: up to the first | or ; or UNMATCHED closing bracket (a balanced {} such as
    xargs -I{} belongs to the arguments)."""
    depth = 0
    for i, c in enumerate(rest):
        if c in "({[":
            depth += 1
        elif c in ")}]":
            if depth == 0:
                return rest[:i]
            depth -= 1
        elif c in "|;" and depth == 0:
            return rest[:i]
    return rest


def _command_positions(seg):
    """(command word, argument text) for each place a command can start in a segment."""
    out = []
    seg = _strip_leaders(seg)
    spans, q, qstart, skip, esc = [], None, 0, False, _esc()
    for i, c in enumerate(seg):                    # quoted text is not a place a command can start
        if skip:
            skip = False
            continue
        if c == esc and q != "'" and (seg[i - 1:i] != ":" or seg[i + 1:i + 2] == esc):
            skip = True
            continue
        if q:
            if c == q:
                spans.append((qstart, i))
                q = None
        elif c in "'\"":
            q, qstart = c, i
    for m in _CMD_POS.finditer(seg):
        if any(a < m.start() < b for a, b in spans):
            continue
        word = re.split(r"[\\/]", m.group(1) or m.group(2))[-1].lower()
        if word.endswith((".exe", ".com")):
            word = word[:-4]
        args = _args_end(seg[m.end():])
        out.append((word, args))
        if word in _PREFIX_WORDS:
            # `timeout 60 find ...`, `nice -n 5 find ...`, `sudo -u me find ...`: an option's value is indistinguishable
            # from the command, so offer every early word as a command position (the unrelated ones match nothing)
            for tm in list(re.finditer(r"\S+", args))[:8]:
                tk = tm.group(0).strip("'\"")
                if tk.startswith("-") or "=" in tk or tk.lower() in ("/c", "/k") or tk.isdigit():
                    continue
                w2 = re.split(r"[\\/]", tk)[-1].lower()
                out.append((w2[:-4] if w2.endswith((".exe", ".com")) else w2, args[tm.end():]))
    return out


def _strip_switch_flags(text):
    """A one-letter /x is a switch, not a drive root (the MSYS form /j), in these shapes only: directly after the word
    mklink (also as a quoted list element: ["cmd", "/c", "mklink", "/J", ...]), anywhere in a statement whose COMMAND is
    a Windows-native tool that takes switches (robocopy, xcopy, mklink, icacls, forfiles, attrib, takeown, findstr, where;
    dir and tree outside the Bash tool, where dir may be GNU dir), and cmd's own /c and /k. A statement that merely
    mentions those words (find /j -iname '*robocopy*') keeps its root."""
    text = re.sub(r"(?i)(\bmklink['\"]\s*,\s*['\"])/[a-z](?=['\"])", r"\1 ", text)          # ["cmd", "/c", "mklink", "/J", ...]
    words = [w for w, _ in _command_positions(text)]
    windows_native = ("robocopy", "xcopy", "mklink", "icacls", "forfiles", "attrib", "takeown", "findstr", "where")
    if any(w in windows_native or (w in ("dir", "tree") and _TOOL_CTX[0] != "Bash") for w in words):
        text = re.sub(r"(?<![\w.:/\\$\-])/[A-Za-z](?![\w.\-/\\])", " ", text)
    if "cmd" in words or re.search(r"(?i)\bcmd(?:\.exe)?['\"]\s*,\s*['\"]/[ck]", text):
        text = re.sub(r"(?i)(?<=\s)/[ck](?=\s)", " ", text)
        text = re.sub(r"(?i)(\bcmd(?:\.exe)?['\"]\s*,\s*['\"])/[ck](?=['\"])", r"\1 ", text)
    return text


def _without_grep_pattern(text, first):
    """For a grep-family command, drop the search PATTERN (the first plain word, or the -e value) so a regex that
    mentions J:/ is not read as a root. rg --files and --type-list take no pattern, so nothing is dropped there."""
    toks = _tokens(text)
    drops = _grep_drops(first, toks)
    return " ".join(t for i, t in enumerate(toks) if i not in drops) if drops else text


def _grep_drops(first, toks):
    """Indexes (into toks, whose first item is the command word) of the pattern tokens of a grep-family command."""
    if first in ("select-string", "sls"):
        # only an explicit -Pattern value is a pattern; the first plain word may be a -Path value
        return {i + 1 for i, t in enumerate(toks) if t.lower() == "-pattern" and i + 1 < len(toks)}
    if first not in _GREPS:
        return set()
    if first == "rg" and any(t in ("--files", "--type-list") for t in toks):
        return set()
    drops, have_pattern = set(), False
    for i, t in enumerate(toks[1:], 1):
        if t in ("-e", "-f", "--regexp", "--file") and i + 1 < len(toks):
            drops.add(i + 1)                                   # -e PATTERN, one per flag
            have_pattern = True
        elif t.startswith(("--regexp=", "--file=")) or (re.match(r"-[ef]", t) and len(t) > 2 and not t.startswith("--")):
            drops.add(i)                                       # the pattern is attached to its flag: -esalary
            have_pattern = True
        elif first == "findstr" and re.match(r"/[cg]:", t, re.IGNORECASE):
            drops.add(i)                                       # findstr /c:"text" or /g:file gives the pattern: no plain word is one
            have_pattern = True
    if not have_pattern:
        for i, t in enumerate(toks[1:], 1):
            if t.startswith("-") or re.fullmatch(r"/[A-Za-z?]{1,3}(?::\S*)?", t):
                continue                                       # a flag (findstr's /s and /i included)
            drops.add(i)                                       # the first plain word is the pattern
            break
    return drops


def _seg_rooted(seg, tool, cwd, first_in_pipe=True, feeds=False):
    seg = _strip_leaders(seg)
    ip = _command_positions(seg)
    first = ip[0][0] if ip else ""
    text = _strip_switch_flags(seg)
    slash_ok = (first in _LISTERS or first in _ALWAYS_RECURSIVE or first in _GREPS or first in ("get-childitem", "gci")
                or (not IS_WINDOWS and first in ("cp", "copy-item")))
    text = _without_grep_pattern(text, first)
    for w, a in ip[1:]:                      # a grep further along (find ... -exec grep -n 'J:' {} +) has a pattern too
        if w in _GREPS or w in ("select-string", "sls"):
            ptoks = _tokens(a)
            for pi in _grep_drops(w, [w] + ptoks):
                for form in ("'" + ptoks[pi - 1] + "'", '"' + ptoks[pi - 1] + '"', ptoks[pi - 1]):
                    if form in text:
                        text = text.replace(form, " ", 1)
                        break
    if first in _PRINTERS and not feeds:
        text = re.sub(r"'[^']*'|\"[^\"]*\"", "''", text)      # a quoted string handed to echo/printf is only printed, unless a pipe passes it on
    if ROOT_ANY.search(text) or _embedded_root(text):
        return True
    has_path, plain_seen = False, 0
    for t in _tokens(text)[1:]:
        if t.startswith("-") or re.fullmatch(r"/[A-Za-z?]{1,3}(?::\S*)?", t):
            continue
        plain_seen += 1
        if t in ("\\", "/") and (not slash_ok or (plain_seen > 1 and IS_WINDOWS)):
            continue                   # a lone slash is division or a separator, unless it is the first argument of a lister
                                       # (any argument of a recursive command on POSIX, where a lone / is the filesystem root)
        if _is_homeish(t):             # ~, $HOME, $env:USERPROFILE, %USERPROFILE%, ~name: the real home directory
            has_path = True
            if any(_is_rooted(loc) for loc in _norm_variants(t, cwd, tool)):
                return True
            continue
        if re.search(r"[$%]", t):
            has_path = True            # a variable path cannot be resolved here; treated as a named path, not as "no path"
            continue
        if re.search(r"[\\/]", t) or t in (".", "..") or re.match(r"^[A-Za-z]:", t):
            has_path = True
            # a directory above a protected folder, or a wildcard under one (J:\*.pdf with a recursion flag walks every folder)
            if any(_is_rooted(loc) for loc in _norm_variants(t, cwd, tool)):
                return True
    return first_in_pipe and (not has_path) and _is_ancestor(cwd)      # a later pipe segment reads stdin, not the cwd


def _depth_limited(word, toks):
    """find -maxdepth 0|1 and rg/fd --max-depth 0|1 list the root's own entries and never enter a child folder. Read
    as real option tokens (a quoted '-d 1' inside a glob does not count), and never with -exec/-ok, whose command
    can walk anywhere."""
    if any(t in ("-exec", "-execdir", "-ok", "-okdir") for t in toks):
        return False
    for i, t in enumerate(toks):
        nxt = toks[i + 1] if i + 1 < len(toks) else ""
        if word == "find" and t == "-maxdepth" and nxt in ("0", "1"):
            return True
        if word != "find" and (t in ("--max-depth", "--maxdepth", "-d") and nxt in ("0", "1")
                               or re.fullmatch(r"--max-?depth=[01]", t)):
            return True
    return False


def _marker(word, args, tool):
    raw = [t.strip("'\"`)}];,") for t in args.split()]        # `& ([scriptblock]::Create('gci J:\ -r'))` leaves -r' attached
    low = [t.lower() for t in raw]
    if word in ("find", "rg", "fd", "fdfind") and _depth_limited(word, _tokens(args)):
        return False
    if word in _ALWAYS_RECURSIVE:
        return True
    if word in ("get-childitem", "gci") or (word in ("ls", "dir") and tool == "PowerShell"):
        if any(re.fullmatch(r"-(?:r|s|rec\w*|depth)(?::\S*)?", t) for t in low):
            return True
    if word == "dir" and "/s" in low:
        return True
    if word in ("copy-item", "cpi", "move-item", "mi", "cp") and any(re.fullmatch(r"-(?:r|rec\w*)", t) for t in low):
        return True
    if word == "cp" and any(re.fullmatch(r"-[A-Za-z]*[rRa][A-Za-z]*", t) for t in raw):
        return True
    if word == "git" and "grep" in low and "--no-index" in low:
        return True
    if word == "ls" and (any(re.fullmatch(r"-[A-Za-z]*R[A-Za-z]*", t) for t in raw) or "--recursive" in low):
        return True
    if word in ("grep", "egrep", "fgrep"):
        if (any(re.fullmatch(r"-[A-Za-z]*[rR][A-Za-z]*", t) for t in raw) or "--recursive" in low
                or "--directories=recurse" in low or ("-d" in low and "recurse" in low)):
            return True
    return (word == "findstr" and "/s" in low) or (word == "where" and "/r" in low) \
        or (word == "forfiles" and "/s" in low) or (word == "icacls" and "/t" in low) \
        or (word == "takeown" and "/r" in low) or (word == "attrib" and "/s" in low)


def _has_marker(infos, seg, tool):
    if any(_marker(w, a, tool) for w, a in infos):
        return True
    return bool(not (infos and infos[0][0] in _QUIET) and _EMBEDDED.search(seg))


def _is_sink(seg, direct, tool):
    low = re.sub(r"&\s*(['\"])([^'\"]*)\1", r"& \2", seg)                         # & "Get-ChildItem" runs the command
    low = re.sub(r"(?i)(/c|-c|-command)\s+(['\"])(.*?)\2", r"\1 \3", low)         # cmd /c "dir ..." runs it too
    low = re.sub(r"'[^']*'|\"[^\"]*\"", "''", low).lower()                        # any other word in a string is not a command
    if re.search(r"(?<![\w-])(?:get-childitem|gci|get-content|gc|get-item|resolve-path|find|ls|dir)(?![\w-])"
                 r"|\[io\.directory\]|system\.io\.directory|getfiles|getdirectories|enumeratefiles"
                 r"|enumeratedirectories", low):
        return True
    if direct and re.search(r"(?<![\w-])select-string(?![\w-])", low):
        return True
    for word, args in _command_positions(seg):
        if word == "xargs":
            plain, skip = [], False
            for t in _tokens(args):
                if skip:
                    skip = False                         # the value of -n 1, -P 4, -I {} ...
                    continue
                if t in ("-n", "-P", "-L", "-I", "-s", "-d", "-E", "-a"):
                    skip = True
                elif not (t.startswith("-") or t.isdigit() or t == "{}"):
                    plain.append(t)
            if plain and plain[0].lower() not in ("echo", "printf", "true", "false"):
                return True            # xargs hands the listing to a command that may open it; xargs echo only prints it
        if word in _GREPS:
            pattern_seen = False
            for t in _tokens(args):
                if re.fullmatch(r"-[A-Za-z]*[rR][A-Za-z]*|--recursive|/s", t, re.IGNORECASE):
                    return True
                if t.startswith("-") or re.fullmatch(r"/[A-Za-z?]{1,3}", t):
                    continue
                if not pattern_seen:
                    pattern_seen = True        # the first plain word is the search pattern, not a path
                    continue
                if re.search(r"[\\/]", t):
                    return True
    return False


def _apply_cd(seg, tool, st):
    toks = _tokens(_strip_leaders(seg))
    if toks[0].lower() in ("popd", "pop-location"):
        st[0] = None
        return
    target, i, rest = None, 0, toks[1:]
    while i < len(rest):
        low = rest[i].lower()
        if low in ("-path", "-literalpath"):
            target = rest[i + 1] if i + 1 < len(rest) else None
            break
        if low.startswith("-") and low != "-" or low == "/d":
            i += 1
            continue
        target = rest[i]
        break
    if target is None:
        st[0] = _home_loc()            # a bare cd goes home (unknown if no home directory resolves)
    elif target == "-":
        st[0] = None
    else:
        st[0] = _riskiest(_norm_variants(target, st[0], tool))


# ---- variables: a root held in a variable, a loop variable or a splat is read where it is used (third review, finding 4)
# A value is only kept when it is plain text (a path, a list of paths): nothing that the shell would read as syntax, so an
# expanded value can never turn into commands, and its length is capped. One expansion budget covers the whole command.
_ASSIGN_WORDS = r"(?:(?:export|declare|local|readonly|typeset)\s+(?:-[A-Za-z]+\s+)*)?"
_BASH_ASSIGN = re.compile(
    r"\s*" + _ASSIGN_WORDS + r"([A-Za-z_]\w*)(\+?)=((?:\"[^\"]*\"|'[^']*'|[^\s;&|<>()\"'])*)")
_BASH_ASSIGN_NAME = re.compile(r"^\s*" + _ASSIGN_WORDS + r"([A-Za-z_]\w*)\+?=")
_BASH_UNSET = re.compile(r"^\s*unset\s+(?:-[vf]\s+)*([A-Za-z_]\w*)")
_PS_REMOVE = re.compile(
    r"^\s*(?:Remove-Variable|rv|Clear-Variable|clv)\s+(?:-Name\s+)?\$?([^\W\d]\w*(?:\s*,\s*\$?[^\W\d]\w*)*)", re.IGNORECASE)
_PS_APPEND = re.compile(r"^\s*\$((?:\w+:)?[^\W\d]\w*)\s*\+=\s*")
_PS_ASSIGN = re.compile(r"^\s*(?:\[[\w.\[\], ]+\]\s*)?\$((?:\w+:)?[^\W\d]\w*)\s*=\s*")
_BASH_FOR = re.compile(r"^\s*for\s+([A-Za-z_]\w*)\s+in\s+")
_PS_FOREACH = re.compile(r"^\s*foreach\s*\(\s*\$([^\W\d]\w*)\s+in\s+", re.IGNORECASE)
_VAR_REF_BASH = re.compile(r"\$\{([A-Za-z_]\w*)(?:[^}\w][^}]*)?\}|\$([A-Za-z_]\w*)(?!\w)")
_VAR_REF_PS = re.compile(
    r"\$\{([^\W\d]\w*)(?:[^}\w][^}]*)?\}|\$((?:\w+:)?[^\W\d]\w*)(?![\w:])|@([^\W\d]\w*)(?![\w:.])")
_ITEM = re.compile(r"\"[^\"]*\"|'[^']*'|[^,\s]+")
_PS_QUOTED_LIST = re.compile(r"^(?:'[^']*'|\"[^\"]*\")(?:\s*,\s*(?:'[^']*'|\"[^\"]*\"))*$")
_VALUE_META = re.compile(r"[&|;<>(){}\r\n$`]")
# A path is never this long; a longer value is a string being built up (b1=$b0$b0 ...), and expanding it grows without limit.
_VALUE_CAP = 1024
_EXPAND_CAP = 8192           # the most characters all expansions of one call may add; past it the call is denied


class _TooLarge(Exception):
    """Variable expansion grew past _EXPAND_CAP."""


def _vk(name, tool):
    """The key a variable is kept under: PowerShell names ignore case and a scope prefix, Bash names are exact."""
    if tool == "PowerShell":
        return re.sub(r"^(?:script|global|local|private):", "", name.lower())
    return name


def _unquote(v):
    v = v.strip()
    return v[1:-1] if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"" else v


def _expand_vars(text, env, tool):
    """`text` with every known variable ($d, ${d}, ${d%/}, $env:P, and a PowerShell splat @a) replaced by the value it was given
    earlier in the same command. A ${d...} modifier is ignored (the value is read as if set). Single-quoted text is left alone
    (neither shell expands it); a variable being assigned to (`$all += ...`) is not a use. Raises _TooLarge when this command's
    expansions have added more than _EXPAND_CAP characters in all (one budget for the whole call: every statement, group, heredoc
    body and text view of it)."""
    if not env or not re.search(r"[$@]", text):
        return text
    rx = _VAR_REF_PS if tool == "PowerShell" else _VAR_REF_BASH
    out, i, q = [], 0, None
    while i < len(text):
        c = text[i]
        if q == "'":
            if c == "'":
                q = None
            out.append(c)
            i += 1
            continue
        if c == "'" and q is None:
            q = "'"
        elif c == '"':
            q = None if q == '"' else '"'
        m = rx.match(text, i) if c in "$@" else None
        if m:
            g = m.groups()
            key = _vk(g[0] or g[1], tool) if (g[0] or g[1]) else "@" + _vk(g[2], tool)
            if key in env and not re.match(r"\s*[+\-*/%]?=(?!=)", text[m.end():m.end() + 4]):
                out.append(env[key])
                _S.expanded += len(env[key])
                if _S.expanded > _EXPAND_CAP:
                    raise _TooLarge()
                i = m.end()
                continue
        out.append(c)
        i += 1
    return "".join(out)


def _splat_text(raw):
    """(arguments, elements) a PowerShell splat or array stands for: `@{Path='J:\\';Recurse=$true}` is (`-Path 'J:\\' -Recurse
    $true`, None), `@('J:\\','-r')` is (`'J:\\' '-r'`, ["'J:\\'", "'-r'"]). None when the text is neither."""
    m = re.match(r"^@\{(.*)\}$", raw, re.S)
    if m:
        pairs = []
        for part in _split_top(m.group(1), "stmt"):
            kv = re.match(r"\s*([A-Za-z_]\w*)\s*=\s*(.+?)\s*$", part, re.S)
            if kv:
                pairs.append("-%s %s" % (kv.group(1), kv.group(2)))
        return " ".join(pairs), None
    m = re.match(r"^@\((.*)\)$", raw, re.S)
    if m:
        items = _ITEM.findall(m.group(1))
        return " ".join(items), items
    return None


def _splat_ok(text):
    """A splat's argument text is safe to keep: short, every quoted piece plain, every bare word a switch, $true/$false/$null or plain."""
    return len(text) <= _VALUE_CAP and all(
        _plain(_unquote(t)) if t[0] in "'\"" else (re.fullmatch(r"-\w+|\$(?:true|false|null)", t, re.IGNORECASE) or _plain(t))
        for t in re.findall(r"\"[^\"]*\"|'[^']*'|\S+", text))


def _plain(v):
    """True when a value is safe to keep: short, and nothing the shell would read as syntax or another variable."""
    return len(v) <= _VALUE_CAP and not _VALUE_META.search(v)


def _ps_value(raw):
    """The text a PowerShell variable holds for this right-hand side, or None when it cannot be known here (an expression, a
    command, another variable, a string with $ in it). A quoted string, a comma list of quoted strings or a bare word is known."""
    raw = raw.strip()
    if _PS_QUOTED_LIST.match(raw):
        items = _ITEM.findall(raw)
        if len(raw) > _VALUE_CAP or not all(_plain(_unquote(t)) for t in items):
            return None
        return _unquote(items[0]) if len(items) == 1 else ",".join(items)
    quoted = len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"" and raw[0] not in raw[1:-1]
    v = raw[1:-1] if quoted else raw
    if not _plain(v) or (not quoted and re.search(r"\s", v)):
        return None
    return v


def _bash_value(raw):
    """The text a Bash assignment gives its variable, quotes removed (`"J:"/x` is `J:/x`); None when it holds a $ or a backtick
    (a variable or a command substitution) or anything the shell reads as syntax."""
    pos, out = 0, []
    for m in re.finditer(r"\"([^\"]*)\"|'([^']*)'|([^\"']+)", raw):
        if m.start() != pos:
            return None
        pos = m.end()
        piece = next(g for g in m.groups() if g is not None)
        if m.group(2) is None and re.search(r"[$`]", piece):
            return None
        out.append(piece)
    if pos != len(raw):
        return None
    v = "".join(out)
    return v if _plain(v) else None


def _literal_items(expr):
    """The items of a loop's list when it is a list of literals (quoted strings, paths, a comma list, @(...)); None when it is a
    command (`Get-ChildItem J:\\ -Directory`: its entries are not the root itself)."""
    expr = expr.strip()
    am = re.match(r"^@\((.*)\)$", expr, re.S)
    if am:
        expr = am.group(1)
    first = re.match(r"\s*([^\s,'\"]+)", expr)
    if first and not re.search(r"[\\/:]", first.group(1)) and not first.group(1).startswith(("$", "@")):
        return None
    return [_unquote(t) for t in _ITEM.findall(expr)]


def _record_assignment(s, tool, env, cwd):
    """Remember what an assignment or a loop header gives its variable, forget a variable that is given something unknown (or is
    unset). `for d in A B`: a rooted item wins, so a loop over a list that holds a root counts as holding it. A variable given
    the listing of a directory above a protected folder is marked ("!name"): a loop over it opens each entry (finding 6)."""
    s = _BLOCK_LEADER.sub("", s)                                         # `then d=...`, `do d=...`, `{ d=...` (a `(` is a subshell: its own variables)
    s = re.sub(r"(?<=\s)#[^\n]*$", "", s)                                # a trailing comment
    m = _BASH_UNSET.match(s) or _PS_REMOVE.match(s)
    if m:
        for name in re.split(r"\s*,\s*", m.group(1)):                  # Remove-Variable q,p forgets both
            for prefix in ("", "@", "!"):
                env.pop(prefix + _vk(name.lstrip("$"), tool), None)
        return
    m = _PS_APPEND.match(s)
    if m:                                                                # $p += x: appends when both parts are plain text
        key = _vk(m.group(1), tool)
        old, v = env.pop(key, None), _ps_value(s[m.end():])
        for k in ("@" + key, "!" + key):
            env.pop(k, None)
        if old is not None and v is not None and not re.search(r"['\",]", old + v) and len(old + v) <= _VALUE_CAP:
            env[key] = old + v
        return
    pos, found = 0, []
    while True:                                                          # `d=A e=1`: several assignments, nothing after them
        m = _BASH_ASSIGN.match(s, pos)
        if not m:
            break
        found.append(m)
        pos = m.end()
    if found and not s[pos:].strip():
        for m in found:
            key = _vk(m.group(1), tool)
            old, v = env.pop(key, None), _bash_value(m.group(3))
            if m.group(2):                                               # d+=x appends: unknown if the old value is
                v = None if v is None or old is None else old + v
                if v is not None and len(v) > _VALUE_CAP:
                    v = None
            if v is not None:
                env[key] = v
        return
    nm = _BASH_ASSIGN_NAME.match(s)
    if nm:                                                               # an assignment we cannot read (d=$(...)): forget the name
        key = _vk(nm.group(1), tool)
        env.pop(key, None)
        env.pop("!" + key, None)
        rhs = s[nm.end():]
        if any(_lists_root(c, tool, cwd) for c in _groups(rhs) + re.findall(r"`([^`]+)`", rhs)):
            env["!" + key] = "1"
        return
    m = _PS_ASSIGN.match(s)
    if m:
        key = _vk(m.group(1), tool)
        for k in (key, "@" + key, "!" + key):
            env.pop(k, None)
        raw = s[m.end():].strip()
        if any(_lists_root(c, tool, cwd) for c in [raw] + _groups(raw)):
            env["!" + key] = "1"
            return
        splat = _splat_text(raw)
        if splat is not None:
            if _splat_ok(splat[0]):
                env["@" + key] = splat[0]
                if splat[1] is not None and _ps_value(",".join(splat[1])) is not None:
                    env[key] = ",".join(splat[1])
            return
        v = _ps_value(raw)
        if v is not None:
            env[key] = v
        return
    items, name = None, None
    m = _BASH_FOR.match(s)
    if m:
        name, items = _vk(m.group(1), tool), [_unquote(t) for t in re.findall(r"\"[^\"]*\"|'[^']*'|\S+", s[m.end():])]
    else:
        m = _PS_FOREACH.match(s)
        gs = _groups(s) if m else []
        if m and gs:
            after = re.split(r"\s+in\s+", gs[0], maxsplit=1)
            name = _vk(m.group(1), tool)
            items = _literal_items(after[1]) if len(after) == 2 else None
    if name is None:
        return
    env.pop(name, None)
    items = [t for t in (items or []) if t and _plain(t)]
    if items:
        rooted = [t for t in items if ROOT_ANY.search(t) or any(_is_rooted(loc) for loc in _norm_variants(t, cwd, tool))]
        env[name] = (rooted or items)[0]


# ---- loops over a root listing, and drive aliases written with a climb (third review, findings 6 and 7)
def _is_lister(word, args):
    """A command that lists the entries of a directory: ls, dir, gci, and find or fd held to the top level."""
    return word in _LISTERS or (word in ("find", "rg", "fd", "fdfind") and _depth_limited(word, _tokens(args)))


def _lists_root(text, tool, cwd):
    """True when `text` is a listing of a directory above a protected folder (a names-only listing is allowed on its own,
    but not as the thing a loop or a command then walks entry by entry)."""
    segs = [x.strip() for x in _split_top(text, "pipe")]
    for i, seg in enumerate(segs):
        ip = _command_positions(seg) if seg else []
        if any(_is_lister(w, a) for w, a in ip) and _seg_rooted(seg, tool, cwd, True, False):
            # a pipe into wc or Measure-Object turns the listing into a number: nothing is opened
            counted = any(w in ("wc", "measure-object", "measure") for later in segs[i + 1:]
                          for w, _ in (_command_positions(later) if later else [])[:1])
            if not counted:
                return True
    return False


_LOOP_SEG = re.compile(r"\s*[({]?\s*(?:while|until|for)\b")
_BLOCK_LEADER = re.compile(r"^\s*(?:(?:do|then|else)\s+|\{\s*)")      # `then for d in ...`, `do for ...`, `{ for ...`


def _loop_header_expr(s):
    """What a loop header iterates over: `for d in <expr>` (Bash) or `foreach ($d in <expr>)` (PowerShell); None otherwise."""
    m = _BASH_FOR.match(_BLOCK_LEADER.sub("", s))
    if m:
        return _BLOCK_LEADER.sub("", s)[m.end():].strip()
    if _PS_FOREACH.match(s):
        gs = _groups(s)
        after = re.split(r"\s+in\s+", gs[0], maxsplit=1) if gs else []
        if len(after) == 2:
            return after[1]
    return None


def _loop_over_root_listing(s, segs, rooted, infos, tool, cwd, env):
    """`for d in $(ls J:/)`, `foreach ($d in Get-ChildItem J:\\)`, `$ds = gci J:\\; foreach ($d in $ds)`, `ls J:/ | while read d`:
    the loop opens what the listing of a directory above the protected folder returns, one entry at a time, so one pass is the
    folder."""
    expr = _loop_header_expr(s)
    if expr is not None:
        inner = _groups(expr) + re.findall(r"`([^`]+)`", expr)       # `$(ls J:/ | wc -l)`: judge what is inside the brackets
        for cand in (inner or [expr]):
            if _lists_root(cand, tool, cwd):
                return True
        if any("!" + _vk(name, tool) in env for name in re.findall(r"\$\{?([^\W\d]\w*)", expr)):
            return True                                # the list is a variable that was given a root listing
    # a rooted listing with a loop (or a loop in a ( ) or { } group) anywhere after it in the pipeline: one pass over the segments
    last_loop = max((j for j, seg in enumerate(segs) if _LOOP_SEG.match(seg)), default=-1)
    if last_loop < 0:
        return False
    return any(rooted[i] and any(_is_lister(w, a) for w, a in infos[i])
               and not any(infos[j] and infos[j][0][0] in ("wc", "measure-object", "measure") for j in range(i + 1, last_loop))
               for i in range(last_loop))                  # `ls J:/ | wc -l | while read n`: a count, nothing is opened


_ALIAS_CMDS = frozenset(("subst", "mklink", "new-psdrive", "ndr", "net", "new-item", "ni"))


def _alias_target_above(s, tool, cwd):
    """A drive alias or junction whose target, once a .. climb or a relative path is resolved, is a directory above a protected
    folder (`subst X: J:\\Claude\\..`, `mklink /J l .` from the drive root). Rule 0d's raw-text check cannot see these."""
    if not any(w in _ALIAS_CMDS for w, _ in _command_positions(s)):      # the word as a grep pattern or in a message is no alias
        return False
    for t in _tokens(_strip_switch_flags(s))[1:]:
        if t.startswith("-") or re.fullmatch(r"[A-Za-z]:", t):       # a flag, or the alias's own drive letter
            continue
        if any(_is_ancestor(loc) for loc in _norm_variants(t, cwd, tool)):
            return True
    return False


def _has_script_block(s):
    """A PowerShell script block: a `{` right after a `)` or after else, try, finally, do, begin, process or end, outside quotes.
    In Bash an if or while condition holds braces of its own (find -exec ... {} +, a brace glob) and never has one."""
    if _TOOL_CTX[0] != "PowerShell":
        return False
    return bool(re.search(r"(?:\)|\b(?:else|try|finally|do|begin|process|end))\s*\{",
                          re.sub(r"'[^']*'|\"[^\"]*\"", "''", s), re.IGNORECASE))


def _words_inside_cached(seg, tool, cwd):
    """_words_inside, remembered per (segment, tool, cwd) for the call being judged: nested scans read the same segment again."""
    key = (seg, tool, cwd)
    hit = _S.inside_cache.get(key)
    if hit is None:
        hit = _S.inside_cache[key] = _words_inside(seg, tool, cwd)
    return hit


def _words_inside(seg, tool, cwd):
    """True when a word of this command (after the command word) resolves, against the cwd, to a place inside a scoped (object)
    entry: `cat companion/identity.md` from the folder above it, `ls work` after a `cd` into the folder's parent. The same
    resolution the recursion rules use (_norm_variants), applied to one more list. A flag is skipped; a `--flag=path` value is not."""
    for word in _SHELL_WORD.findall(_strip_leaders(seg)):
        if len(word) > 1024:
            continue
        t = word
        if _QUOTE_OR_ESC.search(word):
            try:
                t = _strip_shell_quotes(word, tool)     # what the program receives: "work"/x, wo''rk, wo\rk are all work
            except Exception:
                t = word.strip("'\"")
        t = _REDIRECT_OP.sub("", t, count=1)             # <work/x, >work/x, 2>>work/x, and a lone < or > before the target
        if t.startswith("-"):
            m = _PARAM_VALUE.match(t)                    # --file=path, PowerShell -Path:path (a drive letter stays whole)
            t = m.group(1) if m else ""
        if not t:
            continue
        # a wildcard the shell expands; a fully quoted word is no wildcard to Bash (a grep pattern such as '*'), but a cmdlet expands it
        wild = bool(_WILD.search(t)) and not (tool == "Bash" and re.fullmatch(r"'[^']*'|\"[^\"]*\"", word))
        for loc in _norm_variants(t, cwd, tool):
            if _inside(loc) or (wild and isinstance(loc, Loc) and _covers_by_glob(loc.root, loc.parts, True)):
                return True
    return False


_SHELL_WORD = re.compile(r"(?:\"[^\"]*\"|'[^']*'|[^\s\"'])+")
_QUOTE_OR_ESC = re.compile(r"['\"\\`$]")
_REDIRECT_OP =re.compile(r"^\d*[<>]{1,2}&?")
_PARAM_VALUE = re.compile(r"^--?[A-Za-z][\w-]*[=:](.+)$")


def _scan_statement(s, tool, st, depth):
    if not s:
        return False
    try:
        off = _BLOCK_LEADER.match(s)
        off = off.end() if off else 0                   # `then for d in ...`: the loop header starts after the keyword
        core = s[off:]
        m = _PS_ASSIGN.match(core) or _BASH_FOR.match(core)
        if m:                                           # `$p = "$p\x"`, `for d in $d`: only the right-hand side is read with the old value
            s = s[:off + m.end()] + _expand_vars(s[off + m.end():], st[1], tool)
        else:
            m = _PS_FOREACH.match(s)
            gs = _groups(s) if m else []
            if m and gs and s.find(gs[0]) >= 0:         # foreach ($d in <list>) { ... $d ... }: the list is read with the old value,
                he = s.find(gs[0]) + len(gs[0])         # and the body (scanned as its own group) with the one the list gives
                s = s[:m.end()] + _expand_vars(s[m.end():he], st[1], tool) + s[he:]
                st[1].pop(_vk(m.group(1), tool), None)
            else:
                s = _expand_vars(s, st[1], tool)
    except _TooLarge:
        return True                                     # one command that expands past the budget is not read: denied
    _record_assignment(s, tool, st[1], st[0])
    if _ENCODED.search(s):
        return True
    if _ALIAS_VERBS.search(s) and (ROOT_ANY.search(_strip_switch_flags(s)) or _alias_target_above(s, tool, st[0])):
        return True
    segs = [x.strip() for x in _split_top(s, "pipe") if x.strip()]
    if not segs:
        return False
    infos = [_command_positions(seg) for seg in segs]
    if _S.has_scoped and any(_words_inside_cached(seg, tool, st[0]) for seg in segs):
        return True                                     # a path word that lands inside a path-qualified entry
    for seg, ip in zip(segs, infos):
        # Rule 0c, per segment: the name by wildcard. Skipped for commands that only print text (a commit message or an
        # echo that mentions J:\*); a grep-family pattern is dropped first (a regex is not a path).
        first = ip[0][0] if ip else ""
        scan = _without_grep_pattern(seg, first)
        printed = first in _QUIET or first in _PRINTERS or first == ""     # first == "": an expression ($_.Name -like '...'), no command
        if printed:
            scan = re.sub(r"'[^']*'|\"[^\"]*\"", "''", scan)      # a QUOTED wildcard is only printed or compared; an unquoted one is expanded by the shell
        else:
            scan = _clean_for_0c(scan)                            # J:\x\..\P*, /j/./P*, /j/"P"* all name the same folder
        if _name_glob_in(scan):
            return True
        if not printed:
            for t in _tokens(scan):                               # a wildcard path that climbs out with .. (..\P*\x.txt), resolved against the cwd
                if not t.startswith("-") and re.search(r"[*?\[]", t) and re.search(r"(?:^|[\\/])\.\.(?:[\\/]|$)", t):
                    if any(isinstance(p, Loc) and _covers_by_glob(p.root, p.parts) for p in _norm_variants(t, st[0], tool)):
                        return True
    if len(segs) == 1 and infos[0] and infos[0][0][0] in _CD_WORDS and segs[0][0] not in "({$@":
        _apply_cd(segs[0], tool, st)
        return False
    rooted = [_seg_rooted(seg, tool, st[0], i == 0, i + 1 < len(segs) and bool(infos[i + 1]) and infos[i + 1][0][0] in _FEEDS)
              for i, seg in enumerate(segs)]
    # if (...) { ... } / foreach (... in ...) { ... }: the condition and the body are scanned as their own groups below, so
    # a root named in the condition ('J:\') does not make a recursion in the body (over another folder) a root search
    control = bool(re.match(r"\s*(?:if|elseif|else|while|foreach|for|switch|until)\b", s, re.IGNORECASE)) and _has_script_block(s)
    if _loop_over_root_listing(s, segs, rooted, infos, tool, st[0], st[1]):
        return True
    if any(rooted) and not control:
        # a marker counts when its own segment, or a segment feeding it, is rooted: a 'J:\' string in a LATER segment
        # (a Replace or -like argument) does not make an earlier recursion over some other folder a root search
        if any(_has_marker(ip, seg, tool) and any(rooted[:j + 1]) for j, (ip, seg) in enumerate(zip(infos, segs))):
            return True
        for i, seg in enumerate(segs):
            if rooted[i] and any(_is_lister(w, a) for w, a in infos[i]):
                if any(_is_sink(segs[j], j == i + 1, tool) for j in range(i + 1, len(segs))):
                    return True
    if depth < 3:
        for seg, ip in zip(segs, infos):
            if _SHELLOUT.search(seg):
                # os.system('find /j ...'), subprocess.run(['find', '/j', ...]), execSync(...), system("..."): the quoted
                # pieces are the command; scan them one by one and joined (the list form splits the command into pieces)
                quoted = [a or b for a, b in re.findall(r"\"([^\"]*)\"|'([^']*)'", seg)]
                if any(_scan_text(t, "Bash", st[0], depth + 1, st[1]) for t in quoted + [" ".join(quoted)]):
                    return True
            words = [w for w, _ in ip]
            if any(w in _WRAPPERS for w in words) or re.search(r"(?i)scriptblock\]::create|\binvoke-expression\b|\biex\b", seg):
                # the inner command runs under the WRAPPER's flag rules, not the outer tool's
                inner = ("PowerShell" if any(w in ("powershell", "pwsh", "cmd", "start-process") for w in words)
                         else "Bash" if any(w in ("bash", "sh", "wsl") for w in words) else tool)
                nested = [a or b for a, b in re.findall(r"\"([^\"]*)\"|'([^']*)'", seg)]
                tail = re.search(r"\s(?:-c|-command|/c)\s+(.*)$", seg, re.S | re.IGNORECASE)
                if tail:
                    nested.append(tail.group(1))
                nested += [re.sub(r"(?i)^\s*(?:/[ck]|-c|-command)\s+", "", t) for t in nested]    # Start-Process cmd -ArgumentList '/c dir ...'
                if any(_scan_text(t, inner, st[0], depth + 1, st[1]) for t in nested):
                    return True
        if any(_scan_text(g, tool, st[0], depth + 1, st[1]) for g in _groups(s)):
            return True
        if tool != "PowerShell" and "`" in s:        # Bash command substitution: echo `find /j -name x`
            if any(_scan_text(g, "Bash", st[0], depth + 1, st[1]) for g in re.findall(r"`([^`]+)`", s)):
                return True
    return False


def _clean_for_0c(t):
    """Remove quotes and fold ./ and seg/../ so a wildcard hidden behind them is seen where the shell would resolve it."""
    t = t.replace("'", "").replace('"', "")
    for _ in range(12):
        t2 = re.sub(r"[\\/]\.(?=[\\/])", "", t)
        # fold seg/.. but never treat a .. as the segment being folded (../../../P* must keep its climbs)
        t2 = re.sub(r"[\\/](?!\.\.(?:[\\/]|\s|$))[^\\/\s]+[\\/]\.\.(?=[\\/]|\s|$)", "", t2)
        if t2 == t:
            break
        t = t2
    return t


def _scan_text(text, tool, cwd_parts, depth=0, env=None):
    prev = _TOOL_CTX[0]
    _TOOL_CTX[0] = tool
    try:
        return _scan_text_inner(text, tool, cwd_parts, depth, env)
    finally:
        _TOOL_CTX[0] = prev


def _scan_text_inner(text, tool, cwd_parts, depth, env=None):
    if depth > 3:
        return False
    text = re.sub(r"[–—―]", "-", text)           # PowerShell reads an en or em dash as a parameter prefix
    text, bodies = _strip_bodies(_join_continuations(text))
    for body in bodies:
        if _embedded_root(body):
            return True
        if _scan_text(body, tool, cwd_parts, depth + 1):
            return True
    st = [cwd_parts, dict(env or {})]            # the cwd the next statement starts in, and the variables set so far
    return any(_scan_statement(stmt.strip(), tool, st, depth) for stmt in _split_top(text, "stmt"))


def _name_glob_in(text):
    """Rule 0c over text: a path that starts at the root of a protected folder's drive (or its home directory) and
    reaches the folder through a wildcard (J:\\Pr*, /j/{Pr,X}*, C:\\Us*\\me\\sec*). Each level is the folder's own
    segment or one wildcard segment, and at least one wildcard must really match the segment it stands for."""
    for rx, folder, offset in _S.child_res:
        want = _wants(folder)[offset:]
        for m in rx.finditer(text):
            segs = [s for s in re.split(r"[\\/]+", m.group(1)) if s]
            if len(segs) != len(want):
                continue
            wild = False
            for w, seg in zip(want, segs):
                ok, by_wild = _seg_match(w, seg)
                if not ok:
                    break
                wild = wild or by_wild
            else:
                if wild:
                    return True
    return False


def _glob_pattern_hit(pattern, base):
    """A Glob pattern that walks into a protected folder: `**` under a directory above it, or segments that reach it
    through a wildcard."""
    if re.match(r"^(?:[A-Za-z]:|[\\/]{2}|/|~)", pattern):
        locs = _norm_variants(pattern, base, "PowerShell")
    else:
        locs = [Loc(base.root, tuple(_resolve(pattern, base.parts))) if isinstance(base, Loc) else None]
    for loc in locs:
        if not isinstance(loc, Loc):
            continue
        if _covers_by_glob(loc.root, loc.parts) or _inside(loc):
            return True
        for i, seg in enumerate(loc.parts):              # a ** segment walks every folder below the ones before it
            if "**" in seg and _is_ancestor(Loc(loc.root, loc.parts[:i])):
                return True
    return False


def _root_rules_hit(tool_name, tool_input, command, cwd0):
    if os.environ.get("BDC_TEST_RAISE") and os.environ.get("PYTEST_CURRENT_TEST"):
        raise RuntimeError("injected analysis error")      # test-only: pytest sets PYTEST_CURRENT_TEST, a shell never does
    if tool_name in ("Grep", "Glob"):
        if _name_glob_in(command):
            return True
        path = str(tool_input.get("path") or "")
        bases = _norm_variants(path, cwd0, "PowerShell") if path else [cwd0]
        if any(_inside(b) for b in bases):                   # the search starts inside a scoped entry
            return True
        if tool_name == "Grep":
            return any(_is_ancestor(b) for b in bases)
        return any(_glob_pattern_hit(str(tool_input.get("pattern") or ""), b) for b in bases)
    return _scan_text(command, tool_name, cwd0)


def _root_token_seen(command, cwd):
    """Phase 1, plain regexes only (so it cannot fail the way the analysis can): does the call name a directory above a
    protected folder, a wildcard under one, or start in one or on its drive with a way to climb out?"""
    if ROOT_ANY.search(command) or (_S.cwd_anc and _S.cwd_anc.match(cwd.strip())):
        return True
    if any(rx.search(command) for rx in _S.first_wild_res):                          # J:\\P* and friends
        return True
    return bool(_S.cwd_climb and _S.cwd_climb.match(cwd.strip())                      # a cwd on the drive plus a way to climb out
                and re.search(r"(?i)\.\.|\bcd\b|\bpushd\b|\bset-location\b|\bsl\b", command))


def _any_marker(text, tool, depth=0):
    prev = _TOOL_CTX[0]
    _TOOL_CTX[0] = tool                      # the escape and continuation rules follow the tool whose text this is
    try:
        return _any_marker_inner(text, tool, depth)
    finally:
        _TOOL_CTX[0] = prev


def _any_marker_inner(text, tool, depth=0):
    """True when the text holds a recursion marker (find, rg, tree, Get-ChildItem -Recurse, ls -R, cp -r, os.walk ...),
    read the same way the root check reads one, quoted strings and wrappers included. Used only while the config is
    broken, to deny exactly the commands that could walk into a folder nobody can name."""
    if depth > 3:
        return False
    text, bodies = _strip_bodies(_join_continuations(re.sub(r"[–—―]", "-", text)))
    if any(_any_marker(b, tool, depth + 1) for b in bodies):
        return True
    for stmt in _split_top(text, "stmt"):
        segs = [x.strip() for x in _split_top(stmt.strip(), "pipe") if x.strip()]
        infos = [_command_positions(seg) for seg in segs]
        if any(_has_marker(ip, seg, tool) for ip, seg in zip(infos, segs)):
            return True
        for seg in segs:
            nested = [a or b for a, b in re.findall(r"\"([^\"]*)\"|'([^']*)'", seg)]
            tail = re.search(r"\s(?:-c|-command|/c)\s+(.*)$", seg, re.S | re.IGNORECASE)
            if tail:
                nested.append(tail.group(1))
            if any(_any_marker(n, "Bash", depth + 1) for n in nested) or any(_any_marker(g, tool, depth + 1) for g in _groups(seg)):
                return True
    return False


# ---------------------------------------------------------------- messages

def _roots_text():
    out = []
    for f in _S.folders:
        comps = _display_comps(f)
        if f.root == "/":
            places = ["/" + "/".join(comps[:k]) if k else "/" for k in range(len(comps))]
        else:
            places = [f.root[0].upper() + ":" + "".join("\\" + c for c in comps[:k]) + ("" if k else "\\")
                      for k in range(len(comps))]
            places[0] = "the %s: drive root" % f.root[0].upper()
        for p in places:
            if p not in out:
                out.append(p)
    return ", ".join(out[:6]) + (" and more" if len(out) > 6 else "")


def _folders_text():
    return ", ".join("'%s'" % f.display for f in _S.folders[:4]) + (" and more" if len(_S.folders) > 4 else "")


def _example_listing():
    f = _S.folders[0]
    comps = _display_comps(f)
    if f.root == "/":
        return "`ls %s`" % ("/" + "/".join(comps[:-1]) if len(comps) > 1 else "/")
    return "`Get-ChildItem %s:\\%s -Directory`" % (f.root[0].upper(), "\\".join(comps[:-1]))


def guard_message():
    return (
        "Blocked: this call searches recursively from %s, or names a protected folder by a wildcard, so it would walk "
        "into %s (off-limits to Claude Code by standing user instruction). Allowed instead: a names-only listing "
        "(%s), or a search inside one named folder that does not contain it. Anything else: run it yourself with the ! "
        "prefix. (Protected-folder guard: protected_folder_guard.py.)"
        % (_roots_text(), _folders_text(), _example_listing()))


def name_message():
    return (
        "Blocked: this command references the protected folder %s, which is off-limits to Claude Code by standing "
        "user instruction. If you truly need it, run it yourself with the ! prefix. (Protected-folder guard: "
        "protected_folder_guard.py.)" % _folders_text())


def broken_message(problem):
    return (
        "Blocked: the protected-folders config cannot be trusted (%s), so the guard cannot tell which folders are "
        "protected. Until it is fixed every Grep and Glob call and every recursive shell command (find, rg, tree, "
        "ls -R, Get-ChildItem -Recurse, cp -r, tar and the like) is denied. Read and Edit are not blocked: fix the "
        "file, or run the command yourself with the ! prefix." % problem)


# ---------------------------------------------------------------- the entry point

_ANALYSIS_BUDGET_S = 20.0      # well under the hook's own 60 s timeout, which lets the call through
_CHILD_ABOVE = 16384           # characters; a shorter call cannot run for long, so it is judged in this process
_CHILD_ABOVE_VARS = 2048       # ... unless it uses a variable ($ or @): expansion can multiply the text the analysis reads
_JOBS = []                     # Windows job handles, kept open for as long as this process lives


def slow_message():
    return (
        "Blocked: the protected-folder guard could not finish reading this call in %d seconds (a very long or deeply nested "
        "command), so it is denied rather than left to the hook's timeout, which would let it through. Split it into smaller "
        "commands, or run it yourself with the ! prefix. (Protected-folder guard: protected_folder_guard.py.)"
        % int(_ANALYSIS_BUDGET_S))


def _die_with_parent(proc):
    """Windows: put the child in a job object that kills it when this process ends, so a hook killed mid-call (an interrupt, the
    harness's own timeout) does not leave a child running for minutes. Best effort: any failure leaves the child as it was."""
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes

        class _Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

        class _Io(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in ("ReadOps", "WriteOps", "OtherOps", "ReadBytes", "WriteBytes", "OtherBytes")]

        class _Ext(ctypes.Structure):
            _fields_ = [("Basic", _Basic), ("Io", _Io), ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        job = k32.CreateJobObjectW(None, None)
        if not job:
            return
        info = _Ext()
        info.Basic.LimitFlags = 0x2000                    # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)) \
                and k32.AssignProcessToJobObject(job, int(proc._handle)):
            _JOBS.append(job)
    except Exception:
        pass


def _judge_in_child(tool_name, tool_input, cwd, command, argv, env):
    """(verdict, ok). A big call is judged by a child process (this file run with --judge) that is killed when it passes
    _ANALYSIS_BUDGET_S: text matching has input shapes that run for minutes inside one regex call, which holds the interpreter,
    so only another process can stop it. ok is False when no child could be run or it failed; the caller then judges inline."""
    try:
        payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input, "cwd": cwd, "command": command,
                              "argv": list(argv) if argv else None, "env": dict(env) if env is not None else None})
        proc = subprocess.Popen([sys.executable, "-I", os.path.abspath(__file__), "--judge"], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except (OSError, ValueError, TypeError):
        return None, False
    _die_with_parent(proc)
    try:
        out, _ = proc.communicate(payload.encode("ascii"), timeout=_ANALYSIS_BUDGET_S)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        return slow_message(), True                   # the child was killed: this call could not be read in time
    except (OSError, ValueError):
        proc.kill()
        return None, False
    if proc.returncode != 0:
        return None, False
    try:
        verdict = json.loads(out.decode("ascii"))["verdict"]
    except (ValueError, KeyError, TypeError):
        return None, False
    return (verdict, True) if verdict is None or isinstance(verdict, str) and verdict else (None, False)


def evaluate(tool_name, tool_input, cwd, command, argv=None, env=None):
    """None to let the call through, or the text of the deny. `command` is the shell text, or for Grep and Glob the
    path, glob and pattern fields joined with newlines. Never raises: an analysis error denies only when a root token
    was seen by the plain pre-check, and otherwise fails open like the hook's other rules. A call longer than
    _CHILD_ABOVE characters (or _CHILD_ABOVE_VARS when it uses a variable) is judged by a child process with a time budget,
    and one that cannot be read in time is denied (fail closed)."""
    if isinstance(command, str) and (len(command) > _CHILD_ABOVE
                                     or (len(command) > _CHILD_ABOVE_VARS and re.search(r"[$@]", command))):
        verdict, ok = _judge_in_child(tool_name, tool_input, cwd, command, argv, env)
        if ok:
            return verdict
    return _evaluate_inner(tool_name, tool_input, cwd, command, argv, env)


def _evaluate_inner(tool_name, tool_input, cwd, command, argv=None, env=None):
    folders, problem = load_folders(argv, env)
    if problem:
        if tool_name in ("Grep", "Glob"):
            return broken_message(problem)
        try:
            return broken_message(problem) if _any_marker(command, tool_name) else None
        except Exception:
            return broken_message(problem)          # the config is broken and the text could not be read: fail closed
    if not folders:
        return None
    configure(folders)
    _S.expanded = 0
    texts = [command]
    if tool_name in ("Bash", "PowerShell"):
        try:
            decoded = _decode_shell_escapes(command, tool_name)
        except Exception:
            decoded = command         # a decode failure leaves only the raw text to judge, never an error
        if decoded != command:
            texts.append(decoded)     # the same call with $'\x20' and `u{20} spelled out: judged as well, the raw text first
    for text in texts:
        verdict = _evaluate_text(tool_name, tool_input, cwd, text)
        if verdict:
            return verdict
    if tool_name in ("Bash", "PowerShell"):
        try:
            stripped = _strip_shell_quotes(command, tool_name)
        except Exception:
            stripped = command
        if stripped not in texts and _name_hit(stripped):
            return name_message()     # the name once the shell has removed quotes: P\rivate, Pri''vate, Pri"va"te
    return None


def _evaluate_text(tool_name, tool_input, cwd, command):
    if _name_hit(command):
        return name_message()
    cwd = cwd or ""
    seen = _root_token_seen(command, cwd)
    try:
        cwd0 = _norm_parts(cwd, None, "Bash") if cwd else None
        hit = _root_rules_hit(tool_name, tool_input, command, cwd0)
    except Exception:
        hit = seen                    # the analysis broke: deny only if a root token was seen, else fail open
    return guard_message() if hit else None


# Escape spellings a shell turns into other characters before the program sees them. Rule 0 and the root rules read text, so
# 'Private$'\x20'Notes' (Bash ANSI-C quoting) and 'Private`u{20}Notes' (PowerShell) must be read the way the shell will.
_ANSI_C = re.compile(r"\$'((?:[^'\\]|\\.)*)'", re.S)
_ANSI_ESC = re.compile(r"\\(?:x([0-9A-Fa-f]{1,2})|u([0-9A-Fa-f]{1,4})|U([0-9A-Fa-f]{1,8})|([0-7]{1,3})|c(.)|(.))", re.S)
_ANSI_SIMPLE = {"a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v",
                "\\": "\\", "'": "'", '"': '"', "?": "?"}
_PS_UNICODE = re.compile(r"`u\{([0-9A-Fa-f]{1,6})\}")
_PS_ESC = re.compile(r"`(.)", re.S)
_PS_SIMPLE = {"0": "\0", "a": "\a", "b": "\b", "e": "\x1b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v"}


def _chr(code, base):
    try:
        return chr(int(code, base))
    except (ValueError, OverflowError):
        return ""


def _ansi_c_unescape(body):
    def one(m):
        hx, u4, u8, octal, ctl, simple = m.groups()
        if hx:
            return _chr(hx, 16)
        if u4:
            return _chr(u4, 16)
        if u8:
            return _chr(u8, 16)
        if octal:
            return chr(int(octal, 8) & 0xFF)
        if ctl:
            return ""
        return _ANSI_SIMPLE.get(simple, "\\" + simple)
    return _ANSI_ESC.sub(one, body)


def _scan_quotes(text, tool, strip):
    """One left-to-right pass that knows which quotes it is inside, so a `$'` in an earlier single-quoted string ('x$') cannot be
    taken for an ANSI-C opener. Always: an unquoted $'...' becomes the characters it stands for (for the PowerShell tool also one
    inside double quotes, where a nested `bash -c "..."` receives it as an opener). With strip=True it also does Bash quote
    removal the way a shell does before the program sees a word (P\\rivate, Pri''vate, Pri"va"te all become Private); the
    PowerShell tool keeps its backslashes, which are path separators there. Everything else stays byte for byte."""
    ps = tool == "PowerShell"
    out, i, n, state = [], 0, len(text), None
    while i < n:
        c = text[i]
        if state != "'" and c == "$" and text.startswith("$'", i) and (state is None or ps):
            m = _ANSI_C.match(text, i)
            if m:
                out.append(_ansi_c_unescape(m.group(1)))
                i = m.end()
                continue
        if state is None:
            if c == "\\" and i + 1 < n:
                nxt = text[i + 1]
                out.append((nxt if nxt != "\n" else "") if strip and not ps else c + nxt)
                i += 2
                continue
            if c in "'\"":
                state = c
                if not strip:
                    out.append(c)
                i += 1
                continue
        elif state == "'":
            if c == "'":
                state = None
                if not strip:
                    out.append(c)
                i += 1
                continue
        else:
            if c == "\\" and i + 1 < n:
                nxt = text[i + 1]
                out.append(nxt if strip and not ps and nxt in '\\"$`' else c + nxt)
                i += 2
                continue
            if c == '"':
                state = None
                if not strip:
                    out.append(c)
                i += 1
                continue
        out.append(c)
        i += 1
    return "".join(out)


def _ps_escapes(text, tool):
    out = _PS_UNICODE.sub(lambda m: _chr(m.group(1), 16), text)
    if tool == "PowerShell":
        out = _PS_ESC.sub(lambda m: _PS_SIMPLE.get(m.group(1), m.group(1)), out)
    return out


def _decode_shell_escapes(text, tool):
    """`text` with Bash ANSI-C quotes ($'...') and PowerShell backtick escapes (`u{20}, `n, `<char>) replaced by the characters
    they stand for, everything else untouched (quotes stay, so the root rules still read quoted text as quoted). PowerShell's
    plain backtick-before-a-character is dropped only for the PowerShell tool: in Bash a backtick starts a command substitution."""
    return _ps_escapes(_scan_quotes(text, tool, False), tool)


def _strip_shell_quotes(text, tool):
    """The text as the program receives it once the shell has removed quotes and escapes. For rule 0's name match only: applied
    to the root rules it would turn quoted text (a commit message holding `find / -name x`) into a live command."""
    return _ps_escapes(_scan_quotes(text, tool, True), tool)


def _judge_main():
    """--judge: read one call as JSON on stdin, print {"verdict": <text or null>}. Used by _judge_in_child."""
    data = json.loads(sys.stdin.buffer.read().decode("ascii"))
    verdict = _evaluate_inner(data["tool_name"], data["tool_input"], data["cwd"], data["command"], data.get("argv"), data.get("env"))
    sys.stdout.write(json.dumps({"verdict": verdict}))


if __name__ == "__main__" and "--judge" in sys.argv[1:]:
    _judge_main()
