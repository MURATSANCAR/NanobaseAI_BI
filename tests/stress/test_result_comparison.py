from result_comparison import norm


def test_column_roles_are_preserved():
    assert norm([['İstanbul', 'Ankara', 12]]) != norm([['Ankara', 'İstanbul', 12]])
    assert norm([[None]]) != norm([['None']])
    assert norm([[None]]) != norm([['']])
    assert norm([[1], [1]]) != norm([[1]])
    assert norm([['İSTANBUL', 1], ['Ankara', 2]]) == norm([['ankara', 2], ['istanbul', 1]])
