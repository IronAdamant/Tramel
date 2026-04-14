from packages.shared_utils.src.shared_utils.hashing import hash_password
from packages.shared_utils.src.shared_utils.tokens import generate_token
from packages.shared_utils.src.shared_utils.validation import validate_email

def register(email, pwd):
    validate_email(email)
    return generate_token(hash_password(pwd))
