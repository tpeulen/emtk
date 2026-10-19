"""mmCIF highlighting: tags, blocks, loops, quoted values and ``;`` text fields.

A CIF word is anything between whitespace; a quote delimits a value only at a
word's edges, and a text field runs from a ``;`` in column 0 to the next one --
a ``;`` or a ``loop_`` inside it is text.
"""

from emtk.widgets.text_editor import Colorizer, TextEditor, Token, shipped_languages

SRC = """data_demo
# comment
loop_
_flr_experiment.id
1 'Alexa488's dye' 5'-end
;  text; with semicolon
   loop_ inside text
;
_flr_sample.solvent_phase liquid
"""


def _tokens():
    ed = TextEditor(SRC, language=shipped_languages()["mmCIF"])
    Colorizer().update(ed.config, ed.document)
    return {line.text: [Token(c) for c in line.colours] for line in ed.document.lines}


def test_mmcif_is_shipped():
    assert "mmCIF" in shipped_languages()


def test_blocks_loops_tags_and_comments():
    t = _tokens()
    assert set(t["data_demo"]) == {Token.DECLARATION}
    assert set(t["loop_"]) == {Token.KEYWORD}
    assert set(t["_flr_experiment.id"]) == {Token.KNOWN_IDENTIFIER}
    assert set(t["# comment"]) == {Token.COMMENT}


def test_a_quote_inside_a_word_is_not_a_delimiter():
    line = "1 'Alexa488's dye' 5'-end"
    toks = _tokens()[line]
    value = line.index("'Alexa488's dye'")
    assert set(toks[value:value + len("'Alexa488's dye'")]) == {Token.STRING}
    word = line.index("5'-end")
    assert Token.STRING not in toks[word:]


def test_a_text_field_runs_from_column_zero_semicolon_to_the_next():
    t = _tokens()
    assert set(t[";  text; with semicolon"]) == {Token.STRING}
    assert set(t["   loop_ inside text"]) == {Token.STRING}
    assert set(t["_flr_sample.solvent_phase liquid"][:25]) == {Token.KNOWN_IDENTIFIER}
