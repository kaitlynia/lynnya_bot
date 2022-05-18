import constants

def print_box(message: str):
  l = len(message)
  print(
    '┏━' + '━' * l + '━┓',
    '┃ ' + message + ' ┃',
    '┗━' + '━' * l + '━┛',
    sep='\n'
  )

# levenshtein distance function. used to determine word values for chatter rewards
# source: https://devrescue.com/levenshtein-distance-in-python
def leven(x, y):
  n = len(x)
  m = len(y)
  A = [[i + j for j in range(m + 1)] for i in range(n + 1)]

  for i in range(n):
    for j in range(m):
      A[i + 1][j + 1] = min(
        A[i][j + 1] + 1,              # insert
        A[i + 1][j] + 1,              # delete
        A[i][j] + int(x[i] != y[j])   # replace
      )
  return A[n][m]

def log(prefix: str, origin: str, *info: str):
  print(f'{prefix} {origin}{" " * max(1, constants.LOG_COLUMN_WIDTH - len(origin))}{"".join(info)}')