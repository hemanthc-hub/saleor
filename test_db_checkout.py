import sys
sys.path.append('.')
import requests

def test_token_verify():
    url = "http://localhost:8000/graphql/"
    # 1. tokenCreate
    auth_query = """
    mutation TokenAuth($email: String!, $password: String!) {
      tokenCreate(email: $email, password: $password) {
        token
        refreshToken
        errors { field message }
      }
    }
    """
    res1 = requests.post(url, json={"query": auth_query, "variables": {"email": "hemanthc@hegmakart.com", "password": "hegmaDefault@123"}})
    print("TokenCreate response:", res1.text)
    data1 = res1.json().get("data", {}).get("tokenCreate", {})
    token = data1.get("token")
    if not token:
        print("No token received!")
        return

    # 2. tokenVerify
    verify_query = """
    mutation VerifyToken($token: String!) {
      tokenVerify(token: $token) {
        isValid
        user { id email }
      }
    }
    """
    res2 = requests.post(url, json={"query": verify_query, "variables": {"token": token}})
    print("TokenVerify response:", res2.text)

test_token_verify()
