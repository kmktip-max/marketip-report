"""공통 입찰 계산 로직 — scheduler.py 와 pages/자동입찰.py 에서 공유"""


def calc_bid(current_rank, target_rank, current_bid, bid_unit, min_bid, max_bid):
    """
    목표순위 기반 입찰가 조정 (고정 delta 방식).
    반환: (new_bid, status)
    - 순위 낮음 (current > target + 0.5): +min(bid_unit, 500)원
    - 순위 높음 (current < target - 0.5): -min(bid_unit//2, 500)원
    - 목표 근접 (±0.5 이내): 유지
    """
    MAX_SINGLE = 500
    if current_rank is None or current_bid is None:
        return current_bid, "데이터 부족"
    diff = current_rank - target_rank
    if diff > 0.5:
        delta   = min(bid_unit, MAX_SINGLE)
        new_bid = min(current_bid + delta, max_bid)
        status  = "최대입찰 도달" if new_bid >= max_bid else "증액중"
    elif diff < -0.5:
        delta   = min(bid_unit // 2 or bid_unit, MAX_SINGLE)
        new_bid = max(current_bid - delta, min_bid)
        status  = "최소입찰 도달" if new_bid <= min_bid else "감액중"
    else:
        new_bid = current_bid
        status  = "유지"
    return round(new_bid / 10) * 10, status
