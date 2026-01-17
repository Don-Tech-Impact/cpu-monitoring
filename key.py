import secrets
import string

keys = string.ascii_letters + string.digits + string.punctuation
while True:
    password = ''.join(secrets.choice(keys) for i in range(50))
    if (any(c.islower() for c in password) and 
        any(c.isupper() for c in password) and
        sum(c.isdigit() for c in password) >= 3):
        break
    # if (any(c.islower() for c in password) and
    #     any(c.isupper() for c in password)
    #     and sum(c.isdigit() for c in password) >= 3
    #     and any(c in string.punctuation for c in password)):
    #     break

print(password)