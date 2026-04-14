import unittest
from sts2_agent.policy.mcts import MCTS, MCTSState
from typing import Iterable, Any

class TicTacToeState(MCTSState):
    def __init__(self, board=None, player=1):
        self.board = board or [0] * 9
        self.player = player

    def get_legal_actions(self) -> Iterable[Any]:
        return [i for i, x in enumerate(self.board) if x == 0]

    def take_action(self, action: Any) -> 'TicTacToeState':
        new_board = list(self.board)
        new_board[action] = self.player
        return TicTacToeState(new_board, 3 - self.player)

    def is_terminal(self) -> bool:
        return self._check_winner() is not None or 0 not in self.board

    def get_reward(self) -> float:
        winner = self._check_winner()
        if winner == 1:
            return 1.0
        elif winner == 2:
            return -1.0
        return 0.0

    def get_current_player(self) -> int:
        return self.player

    def _check_winner(self):
        win_configs = [
            (0, 1, 2), (3, 4, 5), (6, 7, 8),
            (0, 3, 6), (1, 4, 7), (2, 5, 8),
            (0, 4, 8), (2, 4, 6)
        ]
        for a, b, c in win_configs:
            if self.board[a] == self.board[b] == self.board[c] != 0:
                return self.board[a]
        return None

class TestMCTS(unittest.TestCase):
    def test_mcts_tictactoe(self):
        mcts = MCTS()
        # 1 1 0
        # 2 2 0
        # 0 0 0
        # Player 1 should win at index 2
        state = TicTacToeState([1, 1, 0, 2, 2, 0, 0, 0, 0], 1)
        action = mcts.search(state, 1000)
        self.assertEqual(action, 2)

if __name__ == "__main__":
    unittest.main()
