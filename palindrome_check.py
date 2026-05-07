def is_palindrome(s):
    cleaned = ''.join(char for char in s if char.isalnum())
    return cleaned == cleaned[::-1]

s = input("Enter a string: ")
if is_palindrome(s):
    print("The string is a palindrome.")
else:
    print("The string is not a palindrome.")