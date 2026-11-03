from tests.conftest import auth


def test_register_login_me(client):
    body = {"email": "New@T.io", "password": "Password1!", "full_name": "New User"}
    created = client.post("/api/auth/register", json=body)
    assert created.status_code == 201
    assert created.json()["user"]["role"] == "client"
    login = client.post("/api/auth/login", json={"email": "new@t.io", "password": "Password1!"})
    assert login.status_code == 200
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"})
    assert me.json()["email"] == "new@t.io"


def test_register_cannot_set_role(client):
    body = {"email": "x@t.io", "password": "Password1!", "full_name": "X User", "role": "admin"}
    assert client.post("/api/auth/register", json=body).json()["user"]["role"] == "client"


def test_duplicate_email_and_bad_password(client):
    body = {"email": "x@t.io", "password": "Password1!", "full_name": "X User"}
    client.post("/api/auth/register", json=body)
    assert client.post("/api/auth/register", json={**body, "email": "X@t.io"}).status_code == 409
    assert client.post("/api/auth/login", json={"email": "x@t.io", "password": "wrong-pass"}).status_code == 401


def test_login_is_rate_limited(client):
    client.post("/api/auth/register", json={"email": "x@t.io", "password": "Password1!", "full_name": "X User"})
    statuses = [client.post("/api/auth/login", json={"email": "x@t.io", "password": "bad"}).status_code for _ in range(11)]
    assert statuses[:10] == [401] * 10 and statuses[10] == 429


def test_invalid_token_and_role_guards(client, world):
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get("/api/admin/analytics/overview", headers=auth(world.alice)).status_code == 403
    assert client.get("/api/admin/analytics/overview", headers=auth(world.nail_user)).status_code == 403
    assert client.get("/api/admin/analytics/overview").status_code == 401
    assert client.get("/api/admin/clients", headers=auth(world.admin)).status_code == 200
