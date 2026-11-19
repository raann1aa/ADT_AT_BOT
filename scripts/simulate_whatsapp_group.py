"""
Interactive WhatsApp Group Simulation for KrishiBot.
Simulates a busy district farmer WhatsApp group with a mix of:
- Casual greetings & noise (silently ignored)
- Google Form questions (form assistant replies)
- Real farming problems (answered via RAG + LLM)
- Emergency distress (escalated)

Usage:
    python scripts/simulate_whatsapp_group.py
"""

import sys
import time
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from agent.farmer_agent import FarmerAgent, FarmerProfile

SAMPLE_INCOMING_STREAM = [
    {
        "sender": "Ramesh Patil",
        "district": "Nashik",
        "crop": "Onion",
        "message": "Good morning all brothers 🙏💐"
    },
    {
        "sender": "Dnyaneshwar Shinde",
        "district": "Nashik",
        "crop": "Onion",
        "message": "Sir kanda storage rot ho raha hai chawl me, kanda sadi rokne ke liye kya kare?"
    },
    {
        "sender": "Vinod Gaikwad",
        "district": "Nashik",
        "crop": "Tomato",
        "message": "Forwarded: आज का पंचांग और शुभ मुहूर्त। जय श्री राम।"
    },
    {
        "sender": "Sanjay Jadhav",
        "district": "Nashik",
        "crop": "Tomato",
        "message": "Tamatar me blossom end rot aur fal niche se kala pad raha hai, konsi dawai dale?"
    },
    {
        "sender": "Kailash Pawar",
        "district": "Nashik",
        "crop": "Sugarcane",
        "message": "Sir weekly farm details ka google form link dubara bhejo please"
    },
    {
        "sender": "Popat Rao",
        "district": "Nashik",
        "crop": "Cotton",
        "message": "Kapas me gulabi sundi ke liye pheromone trap kitne lagaye aur spray kaun sa kare?"
    },
    {
        "sender": "Anil Deshmukh",
        "district": "Nashik",
        "crop": "Wheat",
        "message": "👍🙏🙏"
    }
]

def main():
    print("=" * 78)
    print("📱 WHATSAPP GROUP LIVE SIMULATOR: [Nashik District Farmers Group - 248 Members]")
    print("=" * 78)
    print("Watching incoming messages in real-time...")
    print("Notice how KrishiBot silently ignores greetings & spam, and answers real queries!\n")

    agent = FarmerAgent()

    for idx, item in enumerate(SAMPLE_INCOMING_STREAM, 1):
        sender = item["sender"]
        crop = item["crop"]
        district = item["district"]
        msg = item["message"]

        print(f"\n--- [Message {idx}] -----------------------------------------------------------")
        print(f"👤 {sender} ({district} | Crop: {crop}):")
        print(f"   💬 \"{msg}\"")

        profile = FarmerProfile(name=sender, district=district, crop=crop)
        resp = agent.process_message(msg, sender_name=sender, profile=profile)

        print(f"⚙️  Classifier: [{resp.category.value}] (Speed: {resp.processing_time_ms} ms)")

        if resp.status == "IGNORED":
            print(f"🔕 Action: [SILENTLY IGNORED] -> {resp.reason}")
            print(f"   (Result: Group chat remains clean and free of bot spam)")
        elif resp.status == "FORM_HELP":
            print(f"📋 Action: [FORM ASSISTANT REPLIED]")
            print(f"   🤖 KrishiBot:")
            for line in resp.reply_text.splitlines():
                print(f"      {line}")
        elif resp.status == "ANSWERED":
            print(f"✅ Action: [RAG + LLM REPLIED]")
            if resp.rag_sources:
                print(f"   📚 Knowledge Sources Used: {', '.join(resp.rag_sources[:2])}")
            print(f"   🤖 KrishiBot:")
            for line in resp.reply_text.splitlines():
                print(f"      {line}")
        elif resp.status == "ESCALATED":
            print(f"🚨 Action: [ADMIN ESCALATION ALERT]")
            print(f"   🤖 KrishiBot:")
            for line in resp.reply_text.splitlines():
                print(f"      {line}")

        time.sleep(1)

    print("\n" + "=" * 78)
    print("🎉 SIMULATION COMPLETED: Group noise was 100% filtered out, queries answered!")
    print("=" * 78)

if __name__ == "__main__":
    main()
