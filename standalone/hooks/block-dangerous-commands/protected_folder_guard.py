"""Protected-folder guard engine, shared by the PreToolUse hooks that import it (block-dangerous-commands.py).

It decides whether one Bash, PowerShell, Grep or Glob call would walk into a folder the owner has marked protected,
without naming it: `find /j` over a drive that holds the folder, `Get-ChildItem C:\\Users\\me -Recurse` over the
folder's parent, `rg x ~`, a wildcard such as `J:\\Pr*` that expands to the folder, a drive alias (`subst`, a junction)
that points at one of its ancestors. It also denies a command that names the folder at all (rule 0). Text matching
over the raw command, not a real shell parser: best-effort, same philosophy as the hook that calls it. The real
boundary would be an operating-system permission, which is a separate decision.

Config: protected-folders.json, `{"protected_folders": ["<absolute path>", ...]}`.
  * `--config <file>` on the hook's command line names the one file to read; a named file that is missing or broken
    denies. This is how a user-level install should wire it, so the guard does not depend on the hook process
    inheriting any environment variable.
  * Without `--config` the default search reads `${CLAUDE_PROJECT_DIR}/.claude/protected-folders.json` and then
    `${CLAUDE_CONFIG_DIR or ~/.claude}/protected-folders.json` and unions the lists. A file that does not exist is
    skipped; a file that exists but is broken denies.
  * No file found, or an empty list: the guard is off (every function here allows).
Every way a config can be wrong (bad JSON, not a list of strings, a relative or `~` path, a trailing separator, a bare
drive or filesystem root, a glob or regex character in the path, a UNC path, a path that does not exist) is a deny
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
from collections import namedtuple

IS_WINDOWS = os.name == "nt"
CONFIG_NAME = "protected-folders.json"

# A location: root is a lower-case drive ("j:") or "/" (a POSIX root); parts are the segments below it.
Loc = namedtuple("Loc", "root parts")
# One protected folder: display is the path as configured, segs its lower-case segments below root.
Folder = namedtuple("Folder", "display root segs")


class ConfigProblem(Exception):
    """A config file that cannot be trusted. The text names the file and says what is wrong."""


_BAD_PATH_CHARS = re.compile(r'[*?\[\]{}^$|+<>"]')
_DRIVE_PATH = re.compile(r"^([A-Za-z]):(?:[\\/](.*))?$", re.S)


def _canon_config_path(raw):
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
    return Folder(p, root, tuple(s.lower() for s in segs))


def _read_config_file(path):
    """The Folder list one file holds; raise ConfigProblem naming the file when it cannot be trusted."""
    try:
        with open(path, encoding="utf-8-sig") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        raise ConfigProblem("%s is missing" % path)
    except (OSError, UnicodeDecodeError) as e:
        raise ConfigProblem("%s cannot be read (%s)" % (path, e.__class__.__name__))
    except ValueError:
        raise ConfigProblem("%s is not valid JSON" % path)
    if not isinstance(data, dict) or not isinstance(data.get("protected_folders"), list):
        raise ConfigProblem('%s does not hold {"protected_folders": [ ... ]} (a list of strings)' % path)
    out = []
    for entry in data["protected_folders"]:
        try:
            folder = _canon_config_path(entry)
        except ValueError as e:
            raise ConfigProblem("%s: %s" % (path, e))
        if not os.path.exists(folder.display):
            raise ConfigProblem("%s: the path %r does not exist on disk" % (path, folder.display))
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


def load_folders(argv=None, env=None):
    """(folders, problem): the protected folders for this call, or a ConfigProblem message when a config named or
    found cannot be trusted. ([], None) means the guard is off."""
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
            folders.extend(_read_config_file(f))
        return folders, None
    except ConfigProblem as e:
        return [], str(e)


# ---------------------------------------------------------------- state derived from the folders (see configure)

class _State(object):
    folders = ()
    root_any = None
    cwd_anc = None
    child_res = ()
    first_wild_res = ()
    name_re = None
    cwd_climb = None


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


def _forms(root, comps, end):
    """Regex sources that name the directory root/comps in text. With end=True each ends as a complete token (the
    root-token check); with end=False it is a prefix that a path continues from."""
    esc = [re.escape(c) for c in comps]
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


def configure(folders):
    """Compile the text patterns for these folders. Called once per hook call (and per test)."""
    _S.folders = tuple(folders)
    home = _home_loc()
    anc_tokens, cwd_tokens, child = [], [], []
    for f in folders:
        for k in range(len(f.segs)):                        # every proper ancestor, the root first
            comps = _display_comps(f)[:k]
            anc_tokens.extend(_forms(f.root, comps, True))
            cwd_tokens.extend(_forms(f.root, comps, False))
        child.append((f, 0, _forms(f.root, [], False)))
        if home and home.root == f.root and len(home.parts) < len(f.segs) \
                and tuple(p.lower() for p in home.parts) == f.segs[:len(home.parts)]:
            hk = len(home.parts)                          # the home directory is on the way to the folder
            comps = _display_comps(f)[hk:]
            for k in range(len(f.segs) - hk):
                tail = "".join(r"[\\/]+" + re.escape(c) for c in comps[:k])
                anc_tokens.append(r"(?<![\w$])" + _HOME_FORMS + tail + _END + _NOT_NAME)
            child.append((f, hk, [r"(?<![\w$])" + _HOME_FORMS]))
    _S.root_any = re.compile("|".join(anc_tokens), re.IGNORECASE) if anc_tokens else None
    _S.cwd_anc = re.compile("^(?:" + "|".join(cwd_tokens) + r")[\\/]*$", re.IGNORECASE) if cwd_tokens else None
    res, first_wild = [], []
    for f, offset, prefixes in child:
        comps = _display_comps(f)[offset:]
        for pre in prefixes:
            levels = "".join(r"[\\/]+(?:%s|%s)" % (re.escape(c), _WILD_TOKEN) for c in comps)
            res.append((re.compile("(?:" + pre + ")(" + levels + r")(?=[\\/\s'\"|;&)]|$)", re.IGNORECASE), f, offset))
            first_wild.append(re.compile("(?:" + pre + r")[\\/]+(" + _WILD_TOKEN + ")", re.IGNORECASE))
    _S.child_res = tuple(res)
    _S.first_wild_res = tuple(first_wild)
    words = []
    for f in folders:
        name = _display_comps(f)[-1]
        parts = [re.escape(w) for w in re.split(r"[\s_\-]+", name) if w]
        if not re.search(r"[A-Za-z0-9]", name):
            words.append(re.escape(name))
        else:
            words.append(r"(?<![A-Za-z0-9])" + r"[\s_\-]*".join(parts) + r"(?![A-Za-z0-9])")
    _S.name_re = re.compile("|".join(words), re.IGNORECASE)
    drives = sorted({f.root for f in folders if f.root != "/"})
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
    r"\bos\.walk\b|\brglob\b|\bi?glob\s*\([^)]*\*\*|\breaddirSync\b[^)]*recursive|\bAllDirectories\b|\bwalk_files\b"
    r"|\bshutil\.(?:copytree|make_archive)\b")
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
    low = seg.lower()
    if low == want:
        return True, False
    if not _WILD.search(seg):
        return False, False
    expansions, truncated = _expand_braces(low)
    if truncated or any(fnmatch.fnmatchcase(want, e) for e in expansions):
        return True, True
    return False, False


def _covers_by_glob(root, segs):
    """True when the typed segments, from `root`, reach a protected folder through at least one wildcard (J:\\Pr*,
    C:\\Us*\\me\\sec*): every segment up to the folder's depth matches and one of them is a wildcard. The exact
    spelling is rule 0's."""
    for f in _S.folders:
        if f.root != root or len(segs) < len(f.segs):
            continue
        wild = False
        for want, seg in zip(f.segs, segs):
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
    recursive search that starts there walks into it. Wildcard segments count where they could match."""
    if not isinstance(loc, Loc):
        return False
    for f in _S.folders:
        if f.root == loc.root and len(loc.parts) < len(f.segs) \
                and all(_seg_match(want, seg)[0] for want, seg in zip(f.segs, loc.parts)):
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
    if ROOT_ANY.search(text):
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


def _scan_statement(s, tool, st, depth):
    if not s:
        return False
    if _ENCODED.search(s):
        return True
    if _ALIAS_VERBS.search(s) and ROOT_ANY.search(_strip_switch_flags(s)):
        return True
    segs = [x.strip() for x in _split_top(s, "pipe") if x.strip()]
    if not segs:
        return False
    infos = [_command_positions(seg) for seg in segs]
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
    control = bool(re.match(r"\s*(?:if|elseif|else|while|foreach|for|switch|until)\b", s, re.IGNORECASE)) and "{" in s
    if any(rooted) and not control:
        # a marker counts when its own segment, or a segment feeding it, is rooted: a 'J:\' string in a LATER segment
        # (a Replace or -like argument) does not make an earlier recursion over some other folder a root search
        if any(_has_marker(ip, seg, tool) and any(rooted[:j + 1]) for j, (ip, seg) in enumerate(zip(infos, segs))):
            return True
        for i, seg in enumerate(segs):
            if rooted[i] and any(w in _LISTERS for w, _ in infos[i]):
                if any(_is_sink(segs[j], j == i + 1, tool) for j in range(i + 1, len(segs))):
                    return True
    if depth < 3:
        for seg, ip in zip(segs, infos):
            if _SHELLOUT.search(seg):
                # os.system('find /j ...'), subprocess.run(['find', '/j', ...]), execSync(...), system("..."): the quoted
                # pieces are the command; scan them one by one and joined (the list form splits the command into pieces)
                quoted = [a or b for a, b in re.findall(r"\"([^\"]*)\"|'([^']*)'", seg)]
                if any(_scan_text(t, "Bash", st[0], depth + 1) for t in quoted + [" ".join(quoted)]):
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
                if any(_scan_text(t, inner, st[0], depth + 1) for t in nested):
                    return True
        if any(_scan_text(g, tool, st[0], depth + 1) for g in _groups(s)):
            return True
        if tool != "PowerShell" and "`" in s:        # Bash command substitution: echo `find /j -name x`
            if any(_scan_text(g, "Bash", st[0], depth + 1) for g in re.findall(r"`([^`]+)`", s)):
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


def _scan_text(text, tool, cwd_parts, depth=0):
    prev = _TOOL_CTX[0]
    _TOOL_CTX[0] = tool
    try:
        return _scan_text_inner(text, tool, cwd_parts, depth)
    finally:
        _TOOL_CTX[0] = prev


def _scan_text_inner(text, tool, cwd_parts, depth):
    if depth > 3:
        return False
    text = re.sub(r"[–—―]", "-", text)           # PowerShell reads an en or em dash as a parameter prefix
    text, bodies = _strip_bodies(_join_continuations(text))
    for body in bodies:
        if ROOT_ANY.search(body) and _EMBEDDED.search(body):
            return True
        if _scan_text(body, tool, cwd_parts, depth + 1):
            return True
    st = [cwd_parts]
    return any(_scan_statement(stmt.strip(), tool, st, depth) for stmt in _split_top(text, "stmt"))


def _name_glob_in(text):
    """Rule 0c over text: a path that starts at the root of a protected folder's drive (or its home directory) and
    reaches the folder through a wildcard (J:\\Pr*, /j/{Pr,X}*, C:\\Us*\\me\\sec*). Each level is the folder's own
    segment or one wildcard segment, and at least one wildcard must really match the segment it stands for."""
    for rx, folder, offset in _S.child_res:
        want = folder.segs[offset:]
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
        if _covers_by_glob(loc.root, loc.parts):
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

def evaluate(tool_name, tool_input, cwd, command, argv=None, env=None):
    """None to let the call through, or the text of the deny. `command` is the shell text, or for Grep and Glob the
    path, glob and pattern fields joined with newlines. Never raises: an analysis error denies only when a root token
    was seen by the plain pre-check, and otherwise fails open like the hook's other rules."""
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
    if _S.name_re.search(command):
        return name_message()
    cwd = cwd or ""
    seen = _root_token_seen(command, cwd)
    try:
        cwd0 = _norm_parts(cwd, None, "Bash") if cwd else None
        hit = _root_rules_hit(tool_name, tool_input, command, cwd0)
    except Exception:
        hit = seen                    # the analysis broke: deny only if a root token was seen, else fail open
    return guard_message() if hit else None
