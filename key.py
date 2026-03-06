"""
Secure temporary password generator.
Produces a cryptographically secure password meeting all policy requirements:
  - At least 2 uppercase letters
  - At least 2 lowercase letters
  - At least 2 digits
  - At least 2 special characters from !@#$%^&*
  - Default length: 16 characters (minimum 12 enforced)

Usage:
    python key.py                  — generate one password
    python key.py 24               — generate a 24-character password
"""
import secrets
import string
import sys


def generate_password(length: int = 16) -> str:
    """
    Generate a cryptographically secure random password.

    Uses secrets.SystemRandom (backed by os.urandom) for all randomness.
    Guarantees at least one character from each required character class,
    then fills remaining slots randomly before shuffling the result.

    Args:
        length: Total password length (minimum 12 is enforced).

    Returns:
        A password string that satisfies all complexity requirements.
    """
    if length < 12:
        length = 12

    uppercase = string.ascii_uppercase
    lowercase = string.ascii_lowercase
    digits = string.digits
    symbols = "!@#$%^&*"
    all_chars = uppercase + lowercase + digits + symbols

    # Guarantee at least two of each required character class
    required = [
        secrets.choice(uppercase),
        secrets.choice(uppercase),
        secrets.choice(lowercase),
        secrets.choice(lowercase),
        secrets.choice(digits),
        secrets.choice(digits),
        secrets.choice(symbols),
        secrets.choice(symbols),
    ]

    # Fill remaining slots with random characters from the full pool
    remaining = [secrets.choice(all_chars) for _ in range(length - len(required))]

    # Combine and shuffle using a cryptographically secure RNG
    pool = required + remaining
    rng = secrets.SystemRandom()
    rng.shuffle(pool)

    return "".join(pool)


if __name__ == "__main__":
    try:
        pwd_length = int(sys.argv[1]) if len(sys.argv) > 1 else 16
    except ValueError:
        pwd_length = 16

    pwd = generate_password(pwd_length)
    print(pwd)
