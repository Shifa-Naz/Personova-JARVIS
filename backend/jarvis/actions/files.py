"""File actions. All targets come from FileSearchService and stay inside the search roots.

Destructive actions (delete, move) resolve their exact targets in `prepare`,
show a concrete impact summary, and only run what the user confirmed.
Deletion always goes to the OS trash — never `os.remove`.
"""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

from pydantic import Field, model_validator

from jarvis.actions.base import (
    ActionError,
    ActionResult,
    ActionSpec,
    Offer,
    Params,
    PermissionLevel,
    PlanStep,
    Prepared,
)
from jarvis.files.search import KIND_EXTENSIONS, KNOWN_FOLDERS, FileEntry, FileSearchService, normalize_name

KindField = Field(default=None, pattern="^(audio|video|media|image|pdf|document|archive)$")


def _start_of_today() -> float:
    now = datetime.now()
    return datetime(now.year, now.month, now.day).timestamp()


def _describe(entry: FileEntry) -> str:
    return f"{entry.name} in {entry.folder}"


def _known_folder(ctx, name: str | None) -> Path | None:
    if not name:
        return None
    folder = ctx.files.resolve_known_folder(name)
    if folder is None:
        raise ActionError("FOLDER_NOT_FOUND", f"I don't have access to a {name} folder.")
    return folder


def _checked_path(ctx, raw: str) -> Path:
    path = Path(raw).expanduser()
    if not ctx.files.is_within_roots(path):
        raise ActionError("PATH_NOT_ALLOWED", "That location is outside the folders I'm allowed to use.")
    if not path.exists():
        raise ActionError("FILE_NOT_FOUND", f"{path.name} no longer exists.")
    return path.resolve()


# ---- find ----------------------------------------------------------------
class FindParams(Params):
    query: str = Field(default="", max_length=200)
    kind: str | None = KindField
    ext: str | None = Field(default=None, pattern=r"^\.?[a-z0-9]{1,6}$")
    modified_today: bool = False
    folders: bool = False
    folder: str | None = Field(default=None, pattern=f"^({'|'.join(KNOWN_FOLDERS)})$")

    @model_validator(mode="after")
    def needs_criteria(self):
        if len(self.query.strip()) < 2 and not (self.kind or self.ext or self.modified_today or self.folder):
            raise ValueError("give a name of at least 2 characters or a filter")
        return self


def find_file(params: FindParams, ctx, prepared) -> ActionResult:
    results = ctx.files.search(
        params.query,
        kind=params.kind,
        ext=params.ext,
        dirs=params.folders or not (params.kind or params.ext),
        files=not params.folders,
        modified_since=_start_of_today() if params.modified_today else None,
        within=_known_folder(ctx, params.folder),
        sort="latest" if params.modified_today else "relevance",
        limit=10,
    )
    what = params.query or params.ext or params.kind or "files"
    if not results:
        offer = None
        if params.query and ctx.connectivity.online():
            offer = Offer(
                "Would you like me to search online?", [PlanStep(action="search_web", params={"query": params.query})]
            )
        return ActionResult.fail("FILE_NOT_FOUND", f"I couldn't find {what} locally.", offer=offer)

    ctx.session.last_results = [r.path for r in results]
    best = results[0]
    data = {"results": [r.to_dict() for r in results]}
    if len(results) == 1:
        message = f"I found {_describe(best)}."
    else:
        message = f"I found {len(results)} matches. The best match is {_describe(best)}."
    return ActionResult(
        True,
        message,
        data=data,
        offer=Offer(f"Shall I open {best.name}?", [PlanStep(action="open_file", params={"path": best.path})]),
    )


# ---- open ----------------------------------------------------------------
class OpenFileParams(Params):
    query: str = Field(default="", max_length=200)
    path: str | None = Field(default=None, max_length=1000)
    kind: str | None = KindField
    latest: bool = False

    @model_validator(mode="after")
    def needs_target(self):
        if not self.path and len(self.query.strip()) < 2 and not self.latest:
            raise ValueError("give a file name, a path, or ask for the latest file")
        return self


def open_file(params: OpenFileParams, ctx, prepared) -> ActionResult:
    if params.path:
        path = _checked_path(ctx, params.path)
    else:
        results = ctx.files.search(
            params.query, kind=params.kind, dirs=False, sort="latest" if params.latest else "relevance", limit=5
        )
        if not results:
            what = (
                (f"a recent {params.kind} file" if params.kind else "a recent file") if params.latest else params.query
            )
            return ActionResult.fail("FILE_NOT_FOUND", f"I couldn't find {what} on this computer.")
        if not params.latest and _is_tie(params.query, results):
            names = ", ".join(_describe(r) for r in results[:3])
            raise ActionError("AMBIGUOUS", f"Several files match: {names}. Which one should I open?")
        path = Path(results[0].path)
    ctx.platform.open_path(path)
    ctx.session.last_file_path = str(path)
    return ActionResult(True, f"Opening {path.name}.", data={"path": str(path)})


class OpenFolderParams(Params):
    known: str | None = Field(default=None, pattern=f"^({'|'.join(KNOWN_FOLDERS)})$")
    query: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def needs_target(self):
        if not self.known and len(self.query.strip()) < 2:
            raise ValueError("give a known folder or a folder name")
        return self


def open_folder(params: OpenFolderParams, ctx, prepared) -> ActionResult:
    if params.known:
        path = _known_folder(ctx, params.known)
    else:
        results = ctx.files.search(params.query, dirs=True, files=False, limit=3)
        if not results:
            return ActionResult.fail("FOLDER_NOT_FOUND", f"I couldn't find a folder called {params.query}.")
        path = Path(results[0].path)
    ctx.platform.open_path(path)
    return ActionResult(True, f"Opening {path.name or 'your home folder'}.", data={"path": str(path)})


# ---- delete (DESTRUCTIVE) -------------------------------------------------
class DeleteParams(Params):
    query: str = Field(default="", max_length=200)
    folder: str | None = Field(default=None, pattern=f"^({'|'.join(KNOWN_FOLDERS)})$")
    all_in_folder: bool = False
    kind: str | None = KindField

    @model_validator(mode="after")
    def needs_target(self):
        if self.all_in_folder and not self.folder:
            raise ValueError("deleting everything requires a folder")
        if self.folder == "home" and self.all_in_folder:
            raise ValueError("I won't delete everything in your home folder")
        if not self.all_in_folder and len(self.query.strip()) < 2:
            raise ValueError("give a file name of at least 2 characters")
        return self


def prepare_delete(params: DeleteParams, ctx) -> Prepared:
    folder = _known_folder(ctx, params.folder)
    if params.all_in_folder:
        exts = KIND_EXTENSIONS.get(params.kind or "", None)
        targets = sorted(
            str(p)
            for p in folder.iterdir()
            if p.is_file()
            and not p.is_symlink()
            and not p.name.startswith(".")
            and (exts is None or p.suffix.lower() in exts)
        )
        if not targets:
            raise ActionError("FILE_NOT_FOUND", f"There are no matching files in {folder.name}.")
        noun = "file" if len(targets) == 1 else "files"
        summary = f"This would move {len(targets)} {noun} from {folder.name} to the trash."
    else:
        results = ctx.files.search(params.query, kind=params.kind, within=folder, limit=5)
        if not results:
            raise ActionError("FILE_NOT_FOUND", f"I couldn't find {params.query}, so nothing was deleted.")
        if _is_tie(params.query, results):
            names = ", ".join(r.name for r in results[:3])
            raise ActionError("AMBIGUOUS", f"Several files match: {names}. Please say the exact name.")
        targets = [results[0].path]
        summary = f"This would move {_describe(results[0])} to the trash."
    for t in targets:
        if not ctx.files.is_within_roots(Path(t)):
            raise ActionError("PATH_NOT_ALLOWED", "One of those files is outside the folders I'm allowed to use.")
    return Prepared(summary=summary, data={"paths": targets})


def _is_tie(query: str, results: list[FileEntry]) -> bool:
    """True when the two best matches are equally good, so picking one would be a guess."""
    if len(results) < 2:
        return False
    q = normalize_name(query)
    return FileSearchService._score(q, results[0]) == FileSearchService._score(q, results[1])


def delete_files(params: DeleteParams, ctx, prepared: Prepared | None) -> ActionResult:
    if prepared is None:  # the executor always prepares; refuse rather than guess
        raise ActionError("NOT_CONFIRMED", "Deletion needs a confirmed target list.")
    try:
        from send2trash import send2trash
    except ImportError as exc:
        raise ActionError("TRASH_UNAVAILABLE", "Safe deletion isn't available (send2trash is not installed).") from exc
    moved, failed = 0, []
    for raw in prepared.data["paths"]:
        path = Path(raw)
        if not path.exists() or not ctx.files.is_within_roots(path):
            failed.append(path.name)
            continue
        try:
            send2trash(str(path))
            moved += 1
        except OSError:
            failed.append(path.name)
    if moved == 0:
        return ActionResult.fail("DELETE_FAILED", "I couldn't move anything to the trash.")
    message = f"Moved {moved} {'file' if moved == 1 else 'files'} to the trash."
    if failed:
        message += f" {len(failed)} could not be moved."
    return ActionResult(True, message, data={"moved": moved, "failed": failed})


# ---- move (DESTRUCTIVE) ---------------------------------------------------
class MoveParams(Params):
    query: str = Field(min_length=2, max_length=200)
    destination: str = Field(min_length=2, max_length=200)


def prepare_move(params: MoveParams, ctx) -> Prepared:
    results = ctx.files.search(params.query, limit=3)
    if not results:
        raise ActionError("FILE_NOT_FOUND", f"I couldn't find {params.query}.")
    src = Path(results[0].path)
    dest_name = params.destination.lower().removesuffix(" folder").strip()
    dest = ctx.files.resolve_known_folder(dest_name) if dest_name in KNOWN_FOLDERS else None
    if dest is None:
        folders = ctx.files.search(dest_name, dirs=True, files=False, limit=1)
        if not folders:
            raise ActionError("FOLDER_NOT_FOUND", f"I couldn't find a folder called {params.destination}.")
        dest = Path(folders[0].path)
    target = dest / src.name
    if target.exists():
        raise ActionError("FILE_EXISTS", f"{dest.name} already has a file called {src.name}; I won't overwrite it.")
    if not (ctx.files.is_within_roots(src) and ctx.files.is_within_roots(dest)):
        raise ActionError("PATH_NOT_ALLOWED", "That location is outside the folders I'm allowed to use.")
    return Prepared(
        summary=f"This would move {src.name} from {src.parent.name} to {dest.name}.",
        data={"src": str(src), "dest": str(target)},
    )


def move_file(params: MoveParams, ctx, prepared: Prepared | None) -> ActionResult:
    if prepared is None:
        raise ActionError("NOT_CONFIRMED", "Moving needs a confirmed target.")
    src, dest = Path(prepared.data["src"]), Path(prepared.data["dest"])
    if dest.exists():
        return ActionResult.fail("FILE_EXISTS", f"{dest.name} already exists there; nothing was moved.")
    shutil.move(str(src), str(dest))
    return ActionResult(True, f"Moved {src.name} to {dest.parent.name}.", data={"path": str(dest)})


# ---- create / copy / rename ------------------------------------------------
_BAD_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]|^\.+$|^\s|\s$')
DEFAULT_CREATE_PARENT = "documents"


def _valid_name(name: str) -> str:
    name = name.strip()
    if not name or _BAD_NAME.search(name) or len(name) > 120:
        raise ActionError("INVALID_NAME", f"“{name}” isn't a valid file or folder name.")
    return name


def _destination_folder(ctx, raw: str) -> Path:
    name = raw.lower().removesuffix(" folder").strip()
    name = {"photos": "pictures"}.get(name, name)
    if name in KNOWN_FOLDERS:
        folder = _known_folder(ctx, name)
    else:
        hits = ctx.files.search(name, dirs=True, files=False, limit=3)
        if not hits:
            raise ActionError("FOLDER_NOT_FOUND", f"I couldn't find a folder called {raw}.")
        if _is_tie(name, hits):
            raise ActionError(
                "AMBIGUOUS", f"Several folders match: {', '.join(_describe(h) for h in hits[:3])}. Which one?"
            )
        folder = Path(hits[0].path)
    if not ctx.files.is_within_roots(folder):
        raise ActionError("PATH_NOT_ALLOWED", "That location is outside the folders I'm allowed to use.")
    return folder


def _single_file(ctx, query: str, exclude: Path | None = None) -> Path:
    results = ctx.files.search(query, limit=5)
    if exclude is not None:
        outside = [r for r in results if Path(r.path).parent != exclude.resolve()]
        results = outside or results
    if not results:
        raise ActionError("FILE_NOT_FOUND", f"I couldn't find {query}.")
    if _is_tie(query, results):
        raise ActionError(
            "AMBIGUOUS", f"Several files match: {', '.join(_describe(r) for r in results[:3])}. Which one?"
        )
    return Path(results[0].path)


class CreateFolderParams(Params):
    name: str = Field(min_length=1, max_length=120)
    parent: str = Field(default=DEFAULT_CREATE_PARENT, max_length=200)


def create_folder(params: CreateFolderParams, ctx, prepared) -> ActionResult:
    parent = _destination_folder(ctx, params.parent)
    target = parent / _valid_name(params.name)
    if target.exists():
        return ActionResult.fail("FOLDER_EXISTS", f"{parent.name} already has a folder called {target.name}.")
    target.mkdir()
    if not target.is_dir():  # never claim success without checking
        return ActionResult.fail("CREATE_FAILED", f"I couldn't create {target.name}.")
    ctx.files.note_created(target)
    return ActionResult(True, f"Created the folder {target.name} in {parent.name}.", data={"path": str(target)})


# Plain-text files only: nothing JARVIS writes should be runnable or auto-started by the desktop.
TEXT_EXTENSIONS = frozenset(
    ".txt .md .csv .json .log .html .css .js .ts .py .c .h .cpp .java .xml .yaml .yml .ini".split()
)


class CreateFileParams(Params):
    name: str = Field(min_length=1, max_length=120)
    folder: str = Field(default=DEFAULT_CREATE_PARENT, max_length=200)
    content: str = Field(default="", max_length=20000)


def create_file(params: CreateFileParams, ctx, prepared) -> ActionResult:
    name = _valid_name(params.name)
    if not Path(name).suffix:
        name += ".txt"
    if Path(name).suffix.lower() not in TEXT_EXTENSIONS:
        return ActionResult.fail(
            "UNSUPPORTED_FILE_TYPE", f"I only create plain text files, not {Path(name).suffix} files."
        )
    folder = _destination_folder(ctx, params.folder)
    target = folder / name
    if target.exists():
        return ActionResult.fail("FILE_EXISTS", f"{folder.name} already has a file called {name}.")
    body = params.content + ("\n" if params.content and not params.content.endswith("\n") else "")
    with target.open("x", encoding="utf-8") as fh:  # "x": never overwrite something created meanwhile
        fh.write(body)
    if not target.is_file():  # never claim success without checking
        return ActionResult.fail("CREATE_FAILED", f"I couldn't create {name}.")
    ctx.files.note_created(target)
    ctx.session.last_file_path = str(target)
    return ActionResult(
        True,
        f"Created {name} in {folder.name}. It's at {target}.",
        data={"path": str(target), "speech": f"Created {name} in {folder.name}."},
    )


class CopyParams(Params):
    query: str = Field(default="", max_length=200)
    destination: str = Field(default="", max_length=200)
    # Exact paths are used when the user accepts the "replace it?" offer.
    src_path: str | None = Field(default=None, max_length=1000)
    dest_path: str | None = Field(default=None, max_length=1000)
    overwrite: bool = False

    @model_validator(mode="after")
    def needs_targets(self):
        if not (self.src_path or len(self.query.strip()) >= 2):
            raise ValueError("say which file to copy")
        if not (self.dest_path or len(self.destination.strip()) >= 2):
            raise ValueError("say where to copy it")
        return self


def copy_file(params: CopyParams, ctx, prepared) -> ActionResult:
    if params.dest_path:
        dest_dir = _checked_path(ctx, params.dest_path)
        if not dest_dir.is_dir():
            raise ActionError("FOLDER_NOT_FOUND", f"{dest_dir.name} isn't a folder.")
    else:
        dest_dir = _destination_folder(ctx, params.destination)
    # A copy already sitting in the destination isn't a candidate source ("copy it again").
    src = _checked_path(ctx, params.src_path) if params.src_path else _single_file(ctx, params.query, exclude=dest_dir)
    target = dest_dir / src.name
    if target.resolve() == src.resolve():
        return ActionResult.fail("SAME_LOCATION", f"{src.name} is already in {dest_dir.name}.")
    if target.exists() and not params.overwrite:
        return ActionResult.fail(
            "FILE_EXISTS",
            f"{dest_dir.name} already has a file called {src.name}.",
            offer=Offer(
                "Do you want me to replace it?",
                [
                    PlanStep(
                        action="copy_file", params={"src_path": str(src), "dest_path": str(dest_dir), "overwrite": True}
                    )
                ],
            ),
        )
    shutil.copy2(src, target)
    if not target.is_file() or target.stat().st_size != src.stat().st_size:
        return ActionResult.fail("COPY_FAILED", f"Copying {src.name} didn't complete.")
    ctx.files.note_created(target)
    return ActionResult(True, f"Copied {src.name} to {dest_dir.name}.", data={"path": str(target)})


class RenameParams(Params):
    query: str = Field(min_length=2, max_length=200)
    new_name: str = Field(min_length=1, max_length=120)


def prepare_rename(params: RenameParams, ctx) -> Prepared:
    src = _single_file(ctx, params.query)
    new = _valid_name(params.new_name)
    if not Path(new).suffix and src.suffix:
        new += src.suffix  # "rename report.pdf to final" keeps .pdf
    target = src.with_name(new)
    if target.exists():
        raise ActionError("FILE_EXISTS", f"{src.parent.name} already has a file called {new}; I won't overwrite it.")
    return Prepared(
        summary=f"This will rename {src.name} to {new} in {src.parent.name}.",
        data={"src": str(src), "dest": str(target)},
    )


def rename_file(params: RenameParams, ctx, prepared: Prepared | None) -> ActionResult:
    if prepared is None:
        raise ActionError("NOT_CONFIRMED", "Renaming needs a confirmed target.")
    src, dest = Path(prepared.data["src"]), Path(prepared.data["dest"])
    if dest.exists():
        return ActionResult.fail("FILE_EXISTS", f"{dest.name} already exists; nothing was renamed.")
    src.rename(dest)
    if not dest.exists():
        return ActionResult.fail("RENAME_FAILED", f"Renaming {src.name} didn't complete.")
    ctx.files.note_created(dest)
    return ActionResult(True, f"Renamed it to {dest.name}.", data={"path": str(dest)})


SPECS = [
    ActionSpec(
        "find_file",
        "Search local files/folders by name, type, or modified-today.",
        FindParams,
        PermissionLevel.READ_ONLY,
        find_file,
        timeout_s=30,
        examples=("find my react project", "find all jpg files", "show files modified today"),
    ),
    ActionSpec(
        "open_file",
        "Open a local file by name, or the latest file of a kind.",
        OpenFileParams,
        PermissionLevel.SAFE,
        open_file,
        timeout_s=30,
        examples=("open my resume", "open the latest pdf"),
    ),
    ActionSpec(
        "open_folder",
        "Open a folder (downloads, documents, desktop, music, pictures, videos, home, or by name).",
        OpenFolderParams,
        PermissionLevel.SAFE,
        open_folder,
        examples=("open downloads",),
    ),
    ActionSpec(
        "delete_files",
        "Move a file, or all files in a known folder, to the trash.",
        DeleteParams,
        PermissionLevel.DESTRUCTIVE,
        delete_files,
        prepare=prepare_delete,
        timeout_s=60,
    ),
    ActionSpec(
        "move_file",
        "Move a file into another folder.",
        MoveParams,
        PermissionLevel.DESTRUCTIVE,
        move_file,
        prepare=prepare_move,
        timeout_s=60,
    ),
    ActionSpec(
        "create_folder",
        "Create a new folder (default location: Documents).",
        CreateFolderParams,
        PermissionLevel.SAFE,
        create_folder,
        examples=("create folder College",),
    ),
    ActionSpec(
        "create_file",
        "Create a new plain text file, optionally with some text in it (default location: Documents).",
        CreateFileParams,
        PermissionLevel.SAFE,
        create_file,
        examples=("create a file greetings.txt saying hello",),
        sensitive_params=("content",),
    ),
    ActionSpec(
        "copy_file",
        "Copy a file into a folder; never overwrites unless the user agrees.",
        CopyParams,
        PermissionLevel.SAFE,
        copy_file,
        timeout_s=120,
        examples=("copy report.pdf to documents",),
    ),
    ActionSpec(
        "rename_file",
        "Rename a file (keeps its extension if none is given).",
        RenameParams,
        PermissionLevel.SENSITIVE,
        rename_file,
        prepare=prepare_rename,
    ),
]
