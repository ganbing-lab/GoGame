"""
Tests for the improved auto_detect_dead_stones algorithm (two-round detection).
Run from GoGame root: python -m gogame.test_dead_stones

Note: This module imports through gogame.__init__ which requires tkinter.
If testing on a headless system, use the inline test script instead.
"""
import unittest
from gogame.core import GoGame
from gogame.config import COLOR_BLACK, COLOR_WHITE, COLOR_EMPTY, BOARD_SIZE


class TestDeadStoneDetection(unittest.TestCase):
    """Test the two-round dead stone detection."""

    def _make_board(self):
        """Create a fresh GoGame with an empty board."""
        g = GoGame()
        g.board = [[COLOR_EMPTY] * BOARD_SIZE for _ in range(BOARD_SIZE)]
        return g

    def test_single_dead_stone_in_territory(self):
        """A lone stone inside enemy territory with no escape should be dead."""
        g = self._make_board()
        for r in range(8, 13):
            for c in range(8, 13):
                g.board[r][c] = COLOR_BLACK
        for r in range(9, 12):
            for c in range(9, 12):
                g.board[r][c] = COLOR_EMPTY
        g.board[10][10] = COLOR_WHITE
        dead = g.auto_detect_dead_stones()
        self.assertIn((10, 10), dead)

    def test_dead_3stone_group(self):
        """Three stones strung together inside enemy territory should be dead."""
        g = self._make_board()
        for r in range(6, 15):
            for c in range(6, 15):
                g.board[r][c] = COLOR_BLACK
        for r in range(7, 14):
            for c in range(7, 14):
                g.board[r][c] = COLOR_EMPTY
        for pos in [(10, 10), (10, 11), (10, 12)]:
            g.board[pos[0]][pos[1]] = COLOR_WHITE
        dead = g.auto_detect_dead_stones()
        for pos in [(10, 10), (10, 11), (10, 12)]:
            self.assertIn(pos, dead)

    def test_two_eye_life_not_dead(self):
        """A group with 2 separate eyes should NOT be marked dead (false-positive guard)."""
        g = self._make_board()
        for r in range(3, 14):
            for c in range(3, 16):
                g.board[r][c] = COLOR_BLACK
        for r in range(4, 13):
            for c in range(4, 15):
                g.board[r][c] = COLOR_EMPTY
        # White block with 2 clearly separated eyes
        for c in range(6, 11):
            g.board[7][c] = COLOR_WHITE
            g.board[9][c] = COLOR_WHITE
        for r in range(7, 10):
            g.board[r][6] = COLOR_WHITE
            g.board[r][10] = COLOR_WHITE
        g.board[8][8] = COLOR_WHITE  # separates the two eyes
        dead = g.auto_detect_dead_stones()
        live = {(r, c) for r in range(7, 10) for c in range(6, 11)
                if g.board[r][c] == COLOR_WHITE}
        self.assertEqual(dead & live, set())

    def test_both_sides_dead_intruders(self):
        """Dead stones in both black and white territory should both be detected."""
        g = self._make_board()
        # Black territory on left
        for r in range(3, 17):
            for c in range(3, 10):
                g.board[r][c] = COLOR_BLACK
        for r in range(4, 16):
            for c in range(4, 9):
                g.board[r][c] = COLOR_EMPTY
        # White territory on right
        for r in range(3, 17):
            for c in range(11, 17):
                g.board[r][c] = COLOR_WHITE
        for r in range(4, 16):
            for c in range(12, 16):
                g.board[r][c] = COLOR_EMPTY
        g.board[8][6] = COLOR_WHITE    # dead white in black territory
        g.board[8][14] = COLOR_BLACK   # dead black in white territory
        dead = g.auto_detect_dead_stones()
        self.assertIn((8, 6), dead)
        self.assertIn((8, 14), dead)

    def test_empty_board_no_false_positives(self):
        """Empty board should have zero dead stones."""
        g = GoGame()
        dead = g.auto_detect_dead_stones()
        self.assertEqual(len(dead), 0)

    def test_edge_live_group_not_dead(self):
        """A live group at the edge should NOT be marked dead."""
        g = self._make_board()
        for r in range(0, 3):
            for c in range(0, 10):
                g.board[r][c] = COLOR_BLACK
        dead = g.auto_detect_dead_stones()
        for r in range(0, 3):
            for c in range(0, 10):
                self.assertNotIn((r, c), dead)

    def test_dead_group_deep_no_eyes(self):
        """A dead group deep in territory with 0 eyes should be detected."""
        g = self._make_board()
        for r in range(5, 15):
            for c in range(5, 15):
                g.board[r][c] = COLOR_BLACK
        for r in range(6, 14):
            for c in range(6, 14):
                g.board[r][c] = COLOR_EMPTY
        white_positions = [(8, 8), (8, 9), (9, 8), (9, 9), (9, 10)]
        for r, c in white_positions:
            g.board[r][c] = COLOR_WHITE
        dead = g.auto_detect_dead_stones()
        for pos in white_positions:
            self.assertIn(pos, dead)


if __name__ == "__main__":
    unittest.main()
