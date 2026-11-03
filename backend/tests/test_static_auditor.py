
from app.services.static_auditor import SECRET_PATTERNS


def test_detects_hardcoded_password():
    content = 'password = "SuperSecret123"'

    matches = list(SECRET_PATTERNS["hardcoded_password"].finditer(content))

    assert len(matches) == 1


def test_detects_hardcoded_secret():
    content = 'secret = "my-secret-value"'

    matches = list(SECRET_PATTERNS["hardcoded_password"].finditer(content))

    assert len(matches) == 1


def test_ignores_getpass_prompt():
    content = '''
json={
    "email": args.email,
    "password": getpass.getpass("Study account password: "),
},
'''

    matches = list(SECRET_PATTERNS["hardcoded_password"].finditer(content))

    assert matches == []


def test_detects_aws_access_key_pattern():
    content = "AWS_ACCESS_KEY_ID = AKIA1234567890ABCDEF"

    matches = list(SECRET_PATTERNS["aws_access_key"].finditer(content))

    assert len(matches) == 1


def test_ignores_normal_password_variable():
    content = 'password = getpass.getpass("Enter password: ")'

    matches = list(SECRET_PATTERNS["hardcoded_password"].finditer(content))

    assert matches == []
