import unittest


class HumoTest(unittest.TestCase):
    def test_suma(self):
        self.assertEqual(2 + 2, 4)


if __name__ == "__main__":
    unittest.main()
