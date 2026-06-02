from openpair import OpenPair

client = OpenPair()
print("Calling API...")
result = client.call("What is Python? Answer in 2 sentences.")

print()
print("Response:", result.response_text)
print()
print(f"Model:    {result.model_name}")
print(f"Provider: {result.provider}")
print(f"Tier:     {result.tier}")
print(f"Tokens:   {result.input_tokens} in / {result.output_tokens} out")
print(f"Latency:  {result.latency_ms:.0f} ms")
print(f"Cost est: ${result.estimated_cost:.6f}")
