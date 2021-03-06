# -*- coding: utf-8 -*-
#
# This file is part of the python-chess library.
# Copyright (C) 2012-2015 Niklas Fiekas <niklas.fiekas@tu-clausthal.de>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import chess
import itertools
import re
import logging

try:
    import backport_collections as collections
except ImportError:
    import collections


LOGGER = logging.getLogger(__name__)


NAG_NULL = 0

NAG_GOOD_MOVE = 1
"""A good move. Can also be indicated by ``!`` in PGN notation."""

NAG_MISTAKE = 2
"""A mistake. Can also be indicated by ``?`` in PGN notation."""

NAG_BRILLIANT_MOVE = 3
"""A brilliant move. Can also be indicated by ``!!`` in PGN notation."""

NAG_BLUNDER = 4
"""A blunder. Can also be indicated by ``??`` in PGN notation."""

NAG_SPECULATIVE_MOVE = 5
"""A speculative move. Can also be indicated by ``!?`` in PGN notation."""

NAG_DUBIOUS_MOVE = 6
"""A dubious move. Can also be indicated by ``?!`` in PGN notation."""

NAG_FORCED_MOVE = 7
NAG_SINGULAR_MOVE = 8
NAG_WORST_MOVE = 9
NAG_DRAWISH_POSITION = 10
NAG_QUIET_POSITION = 11
NAG_ACTIVE_POSITION = 12
NAG_UNCLEAR_POSITION = 13
NAG_WHITE_SLIGHT_ADVANTAGE = 14
NAG_BLACK_SLIGHT_ADVANTAGE = 15

# TODO: Add more constants for example from
# https://en.wikipedia.org/wiki/Numeric_Annotation_Glyphs

NAG_WHITE_MODERATE_COUNTERPLAY = 132
NAG_BLACK_MODERATE_COUNTERPLAY = 133
NAG_WHITE_DECISIVE_COUNTERPLAY = 134
NAG_BLACK_DECISIVE_COUNTERPLAY = 135
NAG_WHITE_MODERATE_TIME_PRESSURE = 136
NAG_BLACK_MODERATE_TIME_PRESSURE = 137
NAG_WHITE_SEVERE_TIME_PRESSURE = 138
NAG_BLACK_SEVERE_TIME_PRESSURE = 139


TAG_REGEX = re.compile(r"\[([A-Za-z0-9]+)\s+\"(.*)\"\]")

MOVETEXT_REGEX = re.compile(r"""
    (%.*?[\n\r])
    |(\{.*)
    |(\$[0-9]+)
    |(\()
    |(\))
    |(\*|1-0|0-1|1/2-1/2)
    |(
        [NBKRQ]?[a-h]?[1-8]?[\-x]?[a-h][1-8](?:=?[nbrqNBRQ])?
        |--
        |O-O(?:-O)?
        |0-0(?:-0)?
    )
    |([\?!]{1,2})
    """, re.DOTALL | re.VERBOSE)


class GameNode(object):

    def __init__(self):
        self.parent = None
        self.move = None
        self.nags = set()
        self.starting_comment = ""
        self.comment = ""
        self.variations = []

        self.board_cached = None

    def board(self, _cache=True):
        """
        Gets a board with the position of the node.

        It's a copy, so modifying the board will not alter the game.
        """
        if self.board_cached:
            return self.board_cached.copy()

        board = self.parent.board(_cache=False)
        board.push(self.move)

        if _cache:
            self.board_cached = board
            return board.copy()
        else:
            return board

    def san(self):
        """
        Gets the standard algebraic notation of the move leading to this node.

        Do not call this on the root node.
        """
        return self.parent.board().san(self.move)

    def root(self):
        """Gets the root node, i.e. the game."""
        node = self

        while node.parent:
            node = node.parent

        return node

    def end(self):
        """Follows the main variation to the end and returns the last node."""
        node = self

        while node.variations:
            node = node.variations[0]

        return node

    def is_end(self):
        """Checks if this node is the last node in the current variation."""
        return not self.variations

    def starts_variation(self):
        """
        Checks if this node starts a variation (and can thus have a starting
        comment). The root node does not start a variation and can have no
        starting comment.
        """
        if not self.parent or not self.parent.variations:
            return False

        return self.parent.variations[0] != self

    def is_main_line(self):
        """Checks if the node is in the main line of the game."""
        node = self

        while node.parent:
            parent = node.parent

            if not parent.variations or parent.variations[0] != node:
                return False

            node = parent

        return True

    def is_main_variation(self):
        """
        Checks if this node is the first variation from the point of view of its
        parent. The root node also is in the main variation.
        """
        if not self.parent:
            return True

        return not self.parent.variations or self.parent.variations[0] == self

    def variation(self, move):
        """
        Gets a child node by move or index.
        """
        for index, variation in enumerate(self.variations):
            if move == variation.move or index == move or move == variation:
                return variation

        raise KeyError("variation not found")

    def has_variation(self, move):
        """Checks if the given move appears as a variation."""
        return move in (variation.move for variation in self.variations)

    def promote_to_main(self, move):
        """Promotes the given move to the main variation."""
        variation = self.variation(move)
        self.variations.remove(variation)
        self.variations.insert(0, variation)

    def promote(self, move):
        """Moves the given variation one up in the list of variations."""
        variation = self.variation(move)
        i = self.variations.index(variation)
        if i > 0:
            self.variations[i - 1], self.variations[i] = self.variations[i], self.variations[i - 1]

    def demote(self, move):
        """Moves the given variation one down in the list of variations."""
        variation = self.variation(move)
        i = self.variations.index(variation)
        if i < len(self.variations) - 1:
            self.variations[i + 1], self.variations[i] = self.variations[i], self.variations[i + 1]

    def remove_variation(self, move):
        """Removes a variation by move."""
        self.variations.remove(self.variation(move))

    def add_variation(self, move, comment="", starting_comment="", nags=()):
        """Creates a child node with the given attributes."""
        node = GameNode()
        node.move = move
        node.nags = set(nags)
        node.parent = self
        node.comment = comment
        node.starting_comment = starting_comment
        self.variations.append(node)
        return node

    def add_main_variation(self, move, comment=""):
        """
        Creates a child node with the given attributes and promotes it to the
        main variation.
        """
        node = self.add_variation(move, comment=comment)
        self.promote_to_main(move)
        return node

    def accept(self, visitor, _board=None):
        """
        Traverse game nodes in PGN order using the given *visitor*. Returns
        the visitor result.
        """
        board = self.board() if _board is None else _board

        # The mainline move goes first.
        if self.variations:
            main_variation = self.variations[0]
            visitor.visit_move(board, main_variation.move)

            # Visit NAGs.
            for nag in sorted(main_variation.nags):
                visitor.visit_nag(nag)

            # Visit the comment.
            if main_variation.comment:
                visitor.visit_comment(main_variation.comment)

        # Then visit sidelines.
        for variation in itertools.islice(self.variations, 1, None):
            # Start variation.
            visitor.begin_variation()

            # Append starting comment.
            if variation.starting_comment:
                visitor.visit_comment(variation.starting_comment)

            # Visit move.
            visitor.visit_move(board, variation.move)

            # Visit NAGs.
            for nag in sorted(variation.nags):
                visitor.visit_nag(nag)

            # Visit comment.
            if variation.comment:
                visitor.visit_comment(variation.comment)

            # Recursively append the next moves.
            board.push(variation.move)
            variation.accept(visitor, _board=board)
            board.pop()

            # End variation.
            visitor.end_variation()

        # The mainline is continued last.
        if self.variations:
            main_variation = self.variations[0]

            # Recursively append the next moves.
            board.push(main_variation.move)
            main_variation.accept(visitor, _board=board)
            board.pop()

        # Get the result if not called recursively.
        if _board is None:
            return visitor.result()

    def __str__(self):
        return self.accept(StringExporter(columns=None))


class Game(GameNode):
    """
    The root node of a game with extra information such as headers and the
    starting position.

    By default the following 7 headers are provided in an ordered dictionary:

    >>> game = chess.pgn.Game()
    >>> game.headers["Event"]
    '?'
    >>> game.headers["Site"]
    '?'
    >>> game.headers["Date"]
    '????.??.??'
    >>> game.headers["Round"]
    '?'
    >>> game.headers["White"]
    '?'
    >>> game.headers["Black"]
    '?'
    >>> game.headers["Result"]
    '*'

    Also has all the other properties and methods of
    :class:`~chess.pgn.GameNode`.
    """

    def __init__(self):
        super(Game, self).__init__()

        self.headers = collections.OrderedDict()
        self.headers["Event"] = "?"
        self.headers["Site"] = "?"
        self.headers["Date"] = "????.??.??"
        self.headers["Round"] = "?"
        self.headers["White"] = "?"
        self.headers["Black"] = "?"
        self.headers["Result"] = "*"

        self.errors = []

    def board(self, _cache=False):
        """
        Gets the starting position of the game.

        Unless the `SetUp` and `FEN` header tags are set this is the default
        starting position.
        """
        if "FEN" in self.headers and self.headers.get("SetUp", "1") == "1":
            chess960 = self.headers.get("Variant") == "Chess960"
            board = chess.Board(self.headers["FEN"], chess960=chess960)
            board.chess960 = board.chess960 or board.has_chess960_castling_rights()
            return board
        else:
            return chess.Board()

    def setup(self, board):
        """
        Setup a specific starting position. This sets (or resets) the *SetUp*,
        *FEN* and *Variant* header tags.
        """
        try:
            fen = board.fen()
        except AttributeError:
            board = chess.Board(board)
            board.chess960 = board.has_chess960_castling_rights()
            fen = board.fen()

        if fen == chess.STARTING_FEN:
            self.headers.pop("SetUp", None)
            self.headers.pop("FEN", None)
        else:
            self.headers["SetUp"] = "1"
            self.headers["FEN"] = fen

        if board.chess960:
            self.headers["Variant"] = "Chess960"
        else:
            self.headers.pop("Variant", None)

    def accept(self, visitor):
        """
        Traverses the game in PGN order using the given *visitor*. Returns
        the visitor result.
        """
        visitor.begin_game()

        visitor.begin_headers()
        for tagname, tagvalue in self.headers.items():
            visitor.visit_header(tagname, tagvalue)
        visitor.end_headers()

        if self.comment:
            visitor.visit_comment(self.comment)

        super(Game, self).accept(visitor, _board=self.board())

        visitor.visit_result(self.headers["Result"])
        visitor.end_game()
        return visitor.result()

    @classmethod
    def from_board(cls, board):
        """Creates a game from the move stack of a :class:`~chess.Board()`."""
        # Undo all moves.
        switchyard = collections.deque()
        while board.move_stack:
            switchyard.append(board.pop())

        # Setup initial position.
        game = cls()
        game.setup(board)
        node = game

        # Replay all moves.
        while switchyard:
            move = switchyard.pop()
            node = node.add_variation(move)
            board.push(move)

        game.headers["Result"] = board.result()
        return game


class BaseVisitor(object):
    """
    Base class for visitors.

    Use with :func:`chess.pgn.Game.accept()` or
    :func:`chess.pgn.GameNode.accept()`.

    Methods are called in PGN order.
    """

    def begin_game(self):
        """Called at the start of a game."""
        pass

    def end_game(self):
        """Called at the end of a game."""
        pass

    def begin_headers(self):
        """Called at the start of the game headers."""
        pass

    def visit_header(self, tagname, tagvalue):
        """Called for each game header."""
        pass

    def end_headers(self):
        """Called at the end of the game headers."""
        pass

    def begin_variation(self):
        """
        Called at the start of a new variation. It is not called for the
        mainline of the game.
        """
        pass

    def end_variation(self):
        """Concludes a variation."""
        pass

    def visit_comment(self, comment):
        """Called for each comment."""
        pass

    def visit_nag(self, nag):
        """Called for each NAG."""
        pass

    def visit_move(self, board, move):
        """
        Called for each move.

        *board* is the board state before the move. The board state must be
        restored before the traversal continues.
        """
        pass

    def visit_result(self, result):
        """Called at the end of the game with the *Result*-header."""
        pass

    def handle_error(self, error):
        """Called for errors encountered. Defaults to raising an exception."""
        raise error

    def result(self):
        """Called to get the result of the visitor. Defaults to ``None``."""
        return None


class GameModelCreator(BaseVisitor):
    """
    Creates a game model. Default visitor for :func:`~chess.pgn.read_game()`.
    """

    def __init__(self):
        self.game = Game()
        self.found_game = False

        self.variation_stack = collections.deque([self.game])
        self.starting_comment = ""
        self.in_variation = False

    def begin_game(self):
        self.found_game = True

    def visit_header(self, tagname, tagvalue):
        self.game.headers[tagname] = tagvalue

    def visit_nag(self, nag):
        self.variation_stack[-1].nags.add(nag)

    def begin_variation(self):
        self.variation_stack.append(self.variation_stack[-1].parent)
        self.in_variation = False

    def end_variation(self):
        self.variation_stack.pop()

    def visit_result(self, result):
        if self.game.headers.get("Result", "*") == "*":
            self.game.headers["Result"] = result

    def visit_comment(self, comment):
        if self.in_variation or (not self.variation_stack[-1].parent and self.variation_stack[-1].is_end()):
            # Add as a comment for the current node if in the middle of
            # a variation. Add as a comment for the game, if the comment
            # starts before any move.
            new_comment = [self.variation_stack[-1].comment, comment]
            self.variation_stack[-1].comment = "\n".join(new_comment).strip()
        else:
            # Otherwise it is a starting comment.
            new_comment = [self.starting_comment, comment]
            self.starting_comment = "\n".join(new_comment).strip()

    def visit_move(self, board, move):
        self.variation_stack[-1] = self.variation_stack[-1].add_variation(move)
        self.variation_stack[-1].starting_comment = self.starting_comment
        self.starting_comment = ""
        self.in_variation = True

    def handle_error(self, error):
        LOGGER.exception("error during pgn parsing")

    def result(self):
        """
        Returns a :class:`~chess.pgn.Game()` or ``None`` if no game was
        encountered.
        """
        return self.game if self.found_game else None


class StringExporter(BaseVisitor):
    """
    Allows exporting a game as a string.

    >>> exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
    >>> pgn_string = game.accept(exporter)

    Only *columns* characters are written per line. If *columns* is ``None``
    then the entire movetext will be on a single line. This does not affect
    header tags and comments.

    There will be no newlines at the end of the string.
    """

    def __init__(self, columns=80, headers=True, comments=True, variations=True):
        self.columns = columns
        self.headers = headers
        self.comments = comments
        self.variations = variations

        self.force_movenumber = True

        self.lines = []
        self.current_line = ""
        self.variation_depth = 0

    def flush_current_line(self):
        if self.current_line:
            self.lines.append(self.current_line.rstrip())
        self.current_line = ""

    def write_token(self, token):
        if self.columns is not None and self.columns - len(self.current_line) < len(token):
            self.flush_current_line()
        self.current_line += token

    def write_line(self, line=""):
        self.flush_current_line()
        self.lines.append(line.rstrip())

    def begin_game(self):
        self.after_variation = True

    def end_game(self):
        self.write_line()

    def visit_header(self, tagname, tagvalue):
        if self.headers:
            self.write_line("[{0} \"{1}\"]".format(tagname, tagvalue))

    def end_headers(self):
        if self.headers:
            self.write_line()

    def begin_variation(self):
        self.variation_depth += 1

        if self.variations:
            self.write_token("( ")
            self.force_movenumber = True

    def end_variation(self):
        self.variation_depth -= 1

        if self.variations:
            self.write_token(") ")
            self.force_movenumber = True

    def visit_comment(self, comment):
        if self.comments and (self.variations or not self.variation_depth):
            self.write_token("{ " + comment.replace("}", "").strip() + " } ")
            self.force_movenumber = True

    def visit_nag(self, nag):
        if self.comments and (self.variations or not self.variation_depth):
            self.write_token("$" + str(nag) + " ")

    def visit_move(self, board, move):
        if self.variations or not self.variation_depth:
            # Write the move number.
            if board.turn == chess.WHITE:
                self.write_token(str(board.fullmove_number) + ". ")
            elif self.force_movenumber:
                self.write_token(str(board.fullmove_number) + "... ")

            # Write the SAN.
            self.write_token(board.san(move) + " ")

            self.force_movenumber = False

    def visit_result(self, result):
        self.write_token(result + " ")

    def result(self):
        if self.current_line:
            return "\n".join(itertools.chain(self.lines, [self.current_line.rstrip()])).rstrip()
        else:
            return "\n".join(self.lines).rstrip()

    def __str__(self):
        return self.result()


class FileExporter(StringExporter):
    """
    Like a :class:`~chess.pgn.StringExporter`, but games are written directly
    to a text file.

    There will always be a blank line after each game. Handling encodings is up
    to the caller.

    >>> new_pgn = open("new.pgn", "w", encoding="utf-8")
    >>> exporter = chess.pgn.FileExporter(new_pgn)
    >>> game.accept(exporter)
    """

    def __init__(self, handle, columns=80, headers=True, comments=True, variations=True):
        super(FileExporter, self).__init__(columns=columns, headers=headers, comments=comments, variations=variations)
        self.handle = handle

    def flush_current_line(self):
        if self.current_line:
            self.handle.write(self.current_line.rstrip())
            self.handle.write("\n")
        self.current_line = ""

    def write_line(self, line=""):
        self.flush_current_line()
        self.handle.write(line.rstrip())
        self.handle.write("\n")

    def result(self):
        return None

    def __repr__(self):
        return "<FileExporter at {0}>".format(hex(id(self)))

    def __str__(self):
        return self.__repr__()


def read_game(handle, Visitor=GameModelCreator):
    """
    Reads a game from a file opened in text mode.

    >>> pgn = open("data/pgn/kasparov-deep-blue-1997.pgn")
    >>> first_game = chess.pgn.read_game(pgn)
    >>> second_game = chess.pgn.read_game(pgn)
    >>>
    >>> first_game.headers["Event"]
    'IBM Man-Machine, New York USA'

    By using text mode the parser does not need to handle encodings. It is the
    callers responsibility to open the file with the correct encoding.
    PGN files are ASCII or UTF-8 most of the time. So the following should
    cover most relevant cases (ASCII, UTF-8 without BOM, UTF-8 with BOM,
    UTF-8 with encoding errors).

    >>> pgn = open("data/pgn/kasparov-deep-blue-1997.pgn", encoding="utf-8-sig", errors="surrogateescape")

    Use `StringIO` to parse games from a string.

    >>> pgn_string = "1. e4 e5 2. Nf3 *"
    >>>
    >>> try:
    >>>     from StringIO import StringIO # Python 2
    >>> except ImportError:
    >>>     from io import StringIO # Python 3
    >>>
    >>> pgn = StringIO(pgn_string)
    >>> game = chess.pgn.read_game(pgn)

    The end of a game is determined by a completely blank line or the end of
    the file. (Of course blank lines in comments are possible.)

    According to the standard at least the usual 7 header tags are required
    for a valid game. This parser also handles games without any headers just
    fine.

    The parser is relatively forgiving when it comes to errors. It skips over
    tokens it can not parse. Any exceptions are logged.

    Returns the parsed game or ``None`` if the EOF is reached.
    """
    visitor = Visitor()

    dummy_game = Game()
    found_game = False
    found_content = False

    line = handle.readline()

    # Parse game headers.
    while line:
        # Skip empty lines and comments.
        if not line.strip() or line.strip().startswith("%"):
            line = handle.readline()
            continue

        if not found_game:
            visitor.begin_game()
            visitor.begin_headers()

        found_game = True

        # Read header tags.
        tag_match = TAG_REGEX.match(line)
        if tag_match:
            dummy_game.headers[tag_match.group(1)] = tag_match.group(2)
            visitor.visit_header(tag_match.group(1), tag_match.group(2))
        else:
            break

        line = handle.readline()

    if found_game:
        visitor.end_headers()

    # Get the next non-empty line.
    while not line.strip() and line:
        line = handle.readline()

    # Movetext parser state.
    try:
        board_stack = collections.deque([dummy_game.board()])
    except ValueError as error:
        visitor.handle_error(error)
        board_stack = collections.deque([chess.Board()])

    # Parse movetext.
    while line:
        read_next_line = True

        # An empty line is the end of a game.
        if not line.strip() and found_content:
            if found_game:
                visitor.end_game()

            return visitor.result()

        for match in MOVETEXT_REGEX.finditer(line):
            token = match.group(0)

            if token.startswith("%"):
                # Ignore the rest of the line.
                line = handle.readline()
                continue

            if not found_game:
                found_game = True
                visitor.begin_game()

            if token.startswith("{"):
                # Consume until the end of the comment.
                line = token[1:]
                comment_lines = []
                while line and "}" not in line:
                    comment_lines.append(line.rstrip())
                    line = handle.readline()
                end_index = line.find("}")
                comment_lines.append(line[:end_index])
                if "}" in line:
                    line = line[end_index:]
                else:
                    line = ""

                visitor.visit_comment("\n".join(comment_lines).strip())

                # Continue with the current or the next line.
                if line:
                    read_next_line = False
                break
            elif token.startswith("$"):
                # Found a NAG.
                try:
                    nag = int(token[1:])
                except ValueError as error:
                    visitor.handle_error(error)
                else:
                    visitor.visit_nag(nag)
            elif token == "?":
                visitor.visit_nag(NAG_MISTAKE)
            elif token == "??":
                visitor.visit_nag(NAG_BLUNDER)
            elif token == "!":
                visitor.visit_nag(NAG_GOOD_MOVE)
            elif token == "!!":
                visitor.visit_nag(NAG_BRILLIANT_MOVE)
            elif token == "!?":
                visitor.visit_nag(NAG_SPECULATIVE_MOVE)
            elif token == "?!":
                visitor.visit_nag(NAG_DUBIOUS_MOVE)
            elif token == "(":
                if board_stack[-1].move_stack:
                    visitor.begin_variation()

                    board = board_stack[-1].copy()
                    board.pop()
                    board_stack.append(board)
            elif token == ")":
                # Found a close variation token. Always leave at least the
                # root node on the stack.
                if len(board_stack) > 1:
                    visitor.end_variation()
                    board_stack.pop()
            elif token in ["1-0", "0-1", "1/2-1/2", "*"] and len(board_stack) == 1:
                # Found a result token.
                found_content = True
                visitor.visit_result(token)
            else:
                # Found a SAN token.
                found_content = True

                # Replace zeros castling notation.
                if token == "0-0":
                    token = "O-O"
                elif token == "0-0-0":
                    token = "O-O-O"

                # Parse the SAN.
                try:
                    move = board_stack[-1].parse_san(token)
                except ValueError as error:
                    visitor.handle_error(error)
                else:
                    visitor.visit_move(board_stack[-1], move)
                    board_stack[-1].push(move)

        if read_next_line:
            line = handle.readline()

    if found_game:
        visitor.end_game()

    return visitor.result()


def scan_headers(handle):
    """
    Scan a PGN file opened in text mode for game offsets and headers.

    Yields a tuple for each game. The first element is the offset. The second
    element is an ordered dictionary of game headers.

    Since actually parsing many games from a big file is relatively expensive,
    this is a better way to look only for specific games and seek and parse
    them later.

    This example scans for the first game with Kasparov as the white player.

    >>> pgn = open("mega.pgn")
    >>> for offset, headers in chess.pgn.scan_headers(pgn):
    ...     if "Kasparov" in headers["White"]:
    ...         kasparov_offset = offset
    ...         break

    Then it can later be seeked an parsed.

    >>> pgn.seek(kasparov_offset)
    >>> game = chess.pgn.read_game(pgn)

    This also works nicely with generators, scanning lazily only when the next
    offset is required.

    >>> white_win_offsets = (offset for offset, headers in chess.pgn.scan_headers(pgn)
    ...                             if headers["Result"] == "1-0")
    >>> first_white_win = next(white_win_offsets)
    >>> second_white_win = next(white_win_offsets)

    :warning: Be careful when seeking a game in the file while more offsets are
        being generated.
    """
    in_comment = False

    game_headers = None
    game_pos = None

    last_pos = handle.tell()
    line = handle.readline()

    while line:
        # Skip single line comments.
        if line.startswith("%"):
            last_pos = handle.tell()
            line = handle.readline()
            continue

        # Reading a header tag. Parse it and add it to the current headers.
        if not in_comment and line.startswith("["):
            tag_match = TAG_REGEX.match(line)
            if tag_match:
                if game_pos is None:
                    game_headers = collections.OrderedDict()
                    game_headers["Event"] = "?"
                    game_headers["Site"] = "?"
                    game_headers["Date"] = "????.??.??"
                    game_headers["Round"] = "?"
                    game_headers["White"] = "?"
                    game_headers["Black"] = "?"
                    game_headers["Result"] = "*"

                    game_pos = last_pos

                game_headers[tag_match.group(1)] = tag_match.group(2)

                last_pos = handle.tell()
                line = handle.readline()
                continue

        # Reading movetext. Update parser state in_comment in order to skip
        # comments that look like header tags.
        if (not in_comment and "{" in line) or (in_comment and "}" in line):
            in_comment = line.rfind("{") > line.rfind("}")

        # Reading movetext. If there were headers, previously, those are now
        # complete and can be yielded.
        if game_pos is not None:
            yield game_pos, game_headers
            game_pos = None

        last_pos = handle.tell()
        line = handle.readline()

    # Yield the headers of the last game.
    if game_pos is not None:
        yield game_pos, game_headers


def scan_offsets(handle):
    """
    Scan a PGN file opened in text mode for game offsets.

    Yields the starting offsets of all the games, so that they can be seeked
    later. This is just like :func:`~chess.pgn.scan_headers()` but more
    efficient if you do not actually need the header information.

    The PGN standard requires each game to start with an *Event*-tag. So does
    this scanner.
    """
    in_comment = False

    last_pos = handle.tell()
    line = handle.readline()

    while line:
        if not in_comment and line.startswith("[Event \""):
            yield last_pos
        elif (not in_comment and "{" in line) or (in_comment and "}" in line):
            in_comment = line.rfind("{") > line.rfind("}")

        last_pos = handle.tell()
        line = handle.readline()
