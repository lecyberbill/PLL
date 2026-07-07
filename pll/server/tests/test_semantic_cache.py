import pytest
import os
import tempfile
from pathlib import Path
from services.llm_proxy import SemanticLLMCache

def test_semantic_cache_exact_and_similar_match():
    temp_dir = tempfile.gettempdir()
    cache_path = os.path.join(temp_dir, "test_cache.json")
    if os.path.exists(cache_path):
        os.unlink(cache_path)

    cache = SemanticLLMCache(cache_path, threshold=0.8)

    sys_prompt = "You are a helpful assistant."
    messages = [{"role": "user", "content": "How do you calculate the factorial of a number?"}]
    backend = "test_backend"
    model = "test_model"
    response = {"response": "You can use recursion."}

    # Verify miss initially
    assert cache.lookup(sys_prompt, messages, backend, model) is None

    # Store
    cache.store(sys_prompt, messages, backend, model, response)

    # Exact match lookup
    assert cache.lookup(sys_prompt, messages, backend, model) == response

    # Similar match lookup (Jaccard similarity > 0.8)
    similar_messages = [{"role": "user", "content": "How do you calculate the factorial of the number?"}]
    assert cache.lookup(sys_prompt, similar_messages, backend, model) == response

    # Dissimilar match lookup (Jaccard similarity < 0.8)
    dissimilar_messages = [{"role": "user", "content": "What is the capital of France?"}]
    assert cache.lookup(sys_prompt, dissimilar_messages, backend, model) is None

    # Clean up
    if os.path.exists(cache_path):
        os.unlink(cache_path)
