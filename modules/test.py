def fibonacci(n):
    a, b = 0, 1
    for _ in range(n):
        yield a
        a, b = b, a + b

# Генерация первых 10 чисел Фибоначчи
for num in fibonacci(10):
    print(num)
