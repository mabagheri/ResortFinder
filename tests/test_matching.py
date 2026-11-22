from resortfinder.matching import best_match, haversine_km, name_similarity, normalize_name


def test_normalize_drops_generic_words_and_accents():
    assert normalize_name("Hôtel Xcaret México – All-Inclusive Resort & Spa") == "xcaret mexico"


def test_same_hotel_different_spelling_matches():
    assert name_similarity("Hyatt Ziva Cancun", "Hyatt Ziva Cancún - All Inclusive") > 90


def test_different_hotels_do_not_match_by_name_only():
    cands = [{"name": "Hyatt Zilara Cancun"}, {"name": "Riu Palace Peninsula"}]
    assert best_match("Hyatt Ziva Cancun", None, None, cands, lambda c: c["name"]) is None


def test_coordinates_reject_far_away_namesake():
    cands = [{"name": "Grand Palladium", "lat": 20.0, "lng": -87.0}]
    got = best_match("Grand Palladium", 21.1, -86.76, cands, lambda c: c["name"], lambda c: (c["lat"], c["lng"]))
    assert got is None


def test_coordinates_allow_looser_name_match():
    cands = [{"name": "Breathless Cancun Soul Resort & Spa", "lat": 21.1301, "lng": -86.7461},
             {"name": "Dreams Sands Cancun", "lat": 21.1305, "lng": -86.7465}]
    got = best_match("Breathless Cancún Soul", 21.1302, -86.7462, cands, lambda c: c["name"],
                     lambda c: (c["lat"], c["lng"]))
    assert got["name"].startswith("Breathless")


def test_haversine():
    assert abs(haversine_km(0, 0, 0, 1) - 111.19) < 0.1


def test_sister_hotels_next_to_each_other_do_not_match():
    cands = [{"name": "Hyatt Zilara Cancun", "lat": 21.1300, "lng": -86.7460}]
    got = best_match("Hyatt Ziva Cancun", 21.1301, -86.7461, cands, lambda c: c["name"],
                     lambda c: (c["lat"], c["lng"]))
    assert got is None


def test_longer_name_variant_matches_when_close():
    cands = [{"name": "Iberostar Selection Cancun", "lat": 21.07, "lng": -86.77}]
    got = best_match("Iberostar Cancun", 21.0701, -86.7701, cands, lambda c: c["name"],
                     lambda c: (c["lat"], c["lng"]))
    assert got is not None
