from app.strategy import classify_price

def test_classify_price_buy():
    assert classify_price(80, 80, 130) == "買い候補"

def test_classify_price_danger():
    assert classify_price(131, 80, 130) == "危険"

def test_classify_price_watch():
    assert classify_price(100, 80, 130) == "様子見"
