class ConversationState:
    def __init__(self):
        self.facts = {}
        self.confidence = 0.0
        self.done = False

    def update(self, new_info: dict):
        self.facts.update(new_info)
