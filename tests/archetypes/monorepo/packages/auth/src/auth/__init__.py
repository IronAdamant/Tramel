from packages.shared_utils.src.shared_utils.hashing import hash_password
from packages.shared_utils.src.shared_utils.tokens import generate_token

def login(user, pwd):
    return generate_token(hash_password(pwd))
