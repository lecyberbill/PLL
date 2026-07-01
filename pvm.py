# [WFGY] Zone: SAFE | λ: 0.5 | Fallbacks: 1/MockLLMFallback | Action: implement_pvm_prototype
import re
import random

class BeliefState:
    def __init__(self, value, confidence=1.0):
        self.value = value
        self.confidence = confidence

    def __repr__(self):
        return f"BeliefState(value={repr(self.value)}, confidence={self.confidence:.2f})"

class MockLLMEngine:
    def __init__(self):
        # simple classification and semantic distance mocks
        self.knowledge = {
            "booking travel": ["train", "flight", "ticket", "hotel", "travel", "rome", "london"],
            "support": ["help", "broken", "error", "fail", "issue"],
        }

    def compute_similarity(self, text, target):
        # A simple mock similarity based on overlap of words
        words = set(re.findall(r'\w+', text.lower()))
        target_words = set(re.findall(r'\w+', target.lower()))
        
        # Check against simple mock knowledge associations
        score = 0.1
        for kw_cat, kw_list in self.knowledge.items():
            if target.lower() in kw_cat or kw_cat in target.lower():
                matches = sum(1 for w in words if w in kw_list)
                if matches > 0:
                    score += 0.7 * (matches / max(len(words), 1))
        
        # Default fallback overlap
        overlap = len(words.intersection(target_words))
        if overlap > 0:
            score = max(score, overlap / max(len(target_words), 1))
        
        return min(score, 1.0)

    def generate(self, prompt, target_type=None):
        # Mock LLM generation
        print(f"  [LLM Engine Call] Prompt: '{prompt}' | Target: {target_type}")
        if target_type == "Booking":
            # Simple entity extraction heuristic
            text_lower = prompt.lower()
            dest = "Rome" if "rome" in text_lower else "London" if "london" in text_lower else "Unknown"
            date = "Friday" if "friday" in text_lower else "Weekend" if "weekend" in text_lower else "Unknown"
            return {"destination": dest, "date": date, "flexible": True}
        
        if "Classify intent" in prompt:
            text_lower = prompt.lower()
            if any(w in text_lower for w in ["train", "flight", "rome", "london"]):
                return "booking"
            return "support"
            
        return "Processed response by MockLLM"

class PVM:
    """Probabilistic LLM Virtual Machine Prototype"""
    def __init__(self):
        self.variables = {}
        self.llm = MockLLMEngine()

    def set_variable(self, name, value, confidence=1.0):
        self.variables[name] = BeliefState(value, confidence)
        print(f"[PVM] Set {name} = {self.variables[name]}")

    def query_similarity(self, var_name, target):
        if var_name not in self.variables:
            raise ValueError(f"Variable {var_name} not defined.")
        val = self.variables[var_name].value
        sim = self.llm.compute_similarity(val, target)
        print(f"[PVM] Semantic match: '{val}' ~ '{target}' => {sim:.2f}")
        return sim

    def generate_transform(self, input_var, prompt_instruction, target_type=None):
        input_val = self.variables[input_var].value if input_var in self.variables else input_var
        combined_prompt = f"{prompt_instruction} : {input_val}"
        
        # We attempt verification logic (self-correction simulation)
        attempts = 0
        max_attempts = 3
        temp = 0.0
        
        while attempts < max_attempts:
            attempts += 1
            result = self.llm.generate(combined_prompt, target_type)
            
            # Simple verification rule simulation
            success = True
            if target_type == "Booking":
                if result["destination"] == "Unknown":
                    print(f"  [PVM Warning] Verification failed: Destination is unknown. Attempt {attempts} failed.")
                    success = False
            
            if success:
                # Confidence degrades slightly if multiple attempts were needed
                confidence = max(1.0 - (attempts - 1) * 0.2, 0.1)
                return BeliefState(result, confidence)
            
            # Adjust temperature on retry
            temp += 0.3
            print(f"  [PVM Retry] Adjusting temperature to {temp:.1f} and retrying...")
            
        return BeliefState(result, 0.1) # Failed to satisfy constraints fully, low confidence

# Run a demonstration of the execution flow
if __name__ == "__main__":
    print("--- Starting Probabilistic LLM Virtual Machine Demonstration ---")
    pvm = PVM()
    
    # 1. Initialize user message belief state
    pvm.set_variable("user_message", "I need to find a cheap train to Rome this weekend, maybe Friday or Saturday")
    
    # 2. Intent Classification via LLM
    print("\n--- Phase 1: Semantic Intent Classification ---")
    intent_belief = pvm.generate_transform("user_message", "Classify intent: [booking, support, feedback]")
    pvm.set_variable("intent", intent_belief.value, intent_belief.confidence)
    
    # 3. Probabilistic logic check
    booking_similarity = pvm.query_similarity("intent", "booking")
    
    if booking_similarity > 0.8:
        print("\n--- Phase 2: Structured Entity Extraction & Verification ---")
        # Extract Booking structure
        booking_info = pvm.generate_transform("user_message", "Extract booking details", target_type="Booking")
        pvm.set_variable("result", booking_info.value, booking_info.confidence)
        
        print(f"\nFinal Verified Output: {pvm.variables['result']}")
    else:
        print("\n--- Phase 2: Handling support request ---")
        reply = pvm.generate_transform("user_message", "Respond politely as a support agent")
        pvm.set_variable("reply", reply.value, reply.confidence)
