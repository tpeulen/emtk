"""Command-line entry point."""
from __future__ import annotations

import argparse
import pathlib

from autoport.port_file import port_file

def main() -> int:
    ap = argparse.ArgumentParser(description="Port Dear ImGui C++ to emtk Python.")
    ap.add_argument("source", type=pathlib.Path, nargs="+",
                    help="one or more C++ sources: a header with its .cpp")
    ap.add_argument("--module", default=None)
    ap.add_argument("--origin", default="upstream, MIT")
    ap.add_argument("--out", type=pathlib.Path, default=None)
    ap.add_argument("--print", action="store_true")
    ap.add_argument(
        "--embed-cpp", choices=("full", "ref", "none"), default="full",
        help="what to leave where a region resisted the port. 'full' (the "
             "default) writes a path:lo-hi reference and the C++ verbatim, so "
             "finishing the port is reading down the file. 'ref' writes the "
             "reference only -- cheaper to read, and it cannot fall out of "
             "step with the C++ the way a pasted copy does. 'none' writes "
             "neither, which is what the repair loop used to do: cut the only "
             "copy in the file and leave a pass.")
    ap.add_argument(
        "--no-embed-cpp", dest="embed_cpp", action="store_const", const="none",
        help="the same as --embed-cpp none.")
    ap.add_argument(
        "--define", "-D", dest="defines", action="append", default=[],
        metavar="MACRO",
        help="a macro the C++ is built with. `#ifdef MACRO` bodies are kept "
             "only for these; every other `#ifdef` is dead code in the build "
             "being ported, and porting it calls into functions the library "
             "does not have. Repeatable.")
    a = ap.parse_args()
    module = a.module or a.source[0].stem.replace("-", "_")
    text = port_file(list(a.source), module, a.origin,
                     embed_cpp=a.embed_cpp, defines=a.defines)
    if a.print or not a.out:
        print(text)
    else:
        a.out.mkdir(parents=True, exist_ok=True)
        dest = a.out / f"{module}.py"
        dest.write_text(text)
        refs = text.count("# cpp: ")
        embedded = text.count("# cpp| ")
        note = f", {refs} C++ reference(s)" if refs else ""
        note += f", {embedded} embedded line(s)" if embedded else ""
        print(f"{dest}  ({text.count('TODO(autoport)')} TODO(autoport) flags{note})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
