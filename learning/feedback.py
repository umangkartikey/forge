class FeedbackEngine:
    def __init__(self):
        pass

    def evaluate(self, result):
        """
        Convert module result into reward score (0-1).
        Expected result format:
        {
            "success": bool,
            "data": dict,
            "confidence": float
        }
        """

        if not result:
            return 0.0

        success_score = 1.0 if result.get("success") else 0.0
        confidence_score = result.get("confidence", 0.5)

        # Optional: reward richer data
        data_score = min(len(result.get("data", {})) * 0.1, 0.3)

        reward = (0.5 * success_score) + (0.3 * confidence_score) + (0.2 * data_score)

        return min(max(reward, 0.0), 1.0)