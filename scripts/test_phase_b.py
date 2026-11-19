"""
Automated Test Suite for Phase B:
1. Message Classifier Verification (Noise Filtering)
2. Master FarmerAgent End-to-End Execution
Usage:
    python scripts/test_phase_b.py
"""

import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from agent.classifier import WhatsAppMessageClassifier, MessageCategory
from agent.farmer_agent import FarmerAgent, FarmerProfile

CLASSIFIER_TESTS = [
    # GREETINGS & CHATTER (MUST BE IGNORED)
    {"text": "Good morning all farmers 🙏", "expected_cat": MessageCategory.GREETING_OR_CHATTER, "should_reply": False},
    {"text": "सुप्रभात भाईयों 💐", "expected_cat": MessageCategory.GREETING_OR_CHATTER, "should_reply": False},
    {"text": "Ram Ram ji sabhi ko", "expected_cat": MessageCategory.GREETING_OR_CHATTER, "should_reply": False},
    {"text": "जय श्री राम", "expected_cat": MessageCategory.GREETING_OR_CHATTER, "should_reply": False},
    {"text": "🙏🙏👍", "expected_cat": MessageCategory.GREETING_OR_CHATTER, "should_reply": False},
    {"text": "Ok thanks sir", "expected_cat": MessageCategory.GREETING_OR_CHATTER, "should_reply": False},
    {"text": "धन्यवाद", "expected_cat": MessageCategory.GREETING_OR_CHATTER, "should_reply": False},

    # SPAM / FORWARDS (MUST BE IGNORED)
    {"text": "Forwarded as received: आज का सुविचार - कर्म ही पूजा है। शेयर करें।", "expected_cat": MessageCategory.SPAM_OR_FORWARD, "should_reply": False},
    {"text": "Happy Diwali to all group members and family! 🪔", "expected_cat": MessageCategory.SPAM_OR_FORWARD, "should_reply": False},

    # FORM-RELATED (MUST BE HANDLED)
    {"text": "Sir google form link dobara bhejo form nahi khul raha", "expected_cat": MessageCategory.FORM_RELATED, "should_reply": True},
    {"text": "Maine form bhar diya hai", "expected_cat": MessageCategory.FORM_RELATED, "should_reply": True},

    # URGENT DISTRESS (MUST BE ESCALATED)
    {"text": "Fasal barbad ho gayi hai ab suicide karne ke alawa koi rasta nahi bacha", "expected_cat": MessageCategory.URGENT_DISTRESS, "should_reply": True},

    # LEGITIMATE AGRICULTURAL QUERIES (MUST BE ANSWERED)
    {"text": "Gehu me peela ratua rog aa gaya hai kaun sa spray kare?", "expected_cat": MessageCategory.FARMING_QUERY, "should_reply": True},
    {"text": "कपास में गुलाबी सुंडी का प्रकोप है, कौन सी दवा डालें?", "expected_cat": MessageCategory.FARMING_QUERY, "should_reply": True},
    {"text": "PM kisan installment eKYC kaise update kare?", "expected_cat": MessageCategory.FARMING_QUERY, "should_reply": True},
    {"text": "Pyaj me kanda sadi storage rot rokne ke upay bataye", "expected_cat": MessageCategory.FARMING_QUERY, "should_reply": True},
]

def run_classifier_tests():
    print("=" * 80)
    print("🧪 1. TESTING MESSAGE CLASSIFIER (NOISE FILTERING ENGINE)")
    print("=" * 80)

    classifier = WhatsAppMessageClassifier()
    passed = 0
    total = len(CLASSIFIER_TESTS)

    for idx, test in enumerate(CLASSIFIER_TESTS, 1):
        msg = test["text"]
        expected_cat = test["expected_cat"]
        expected_reply = test["should_reply"]

        result = classifier.classify(msg)
        is_cat_correct = result.category == expected_cat
        is_reply_correct = result.should_reply == expected_reply

        if is_cat_correct and is_reply_correct:
            passed += 1
            action_tag = "REPLY" if result.should_reply else "IGNORE"
            print(f"[{idx:02d}/{total}] ✅ PASS: [{result.category.value}] -> Action: {action_tag}")
            print(f"      Text: \"{msg[:65]}...\"")
        else:
            print(f"[{idx:02d}/{total}] ❌ FAIL:")
            print(f"      Text: \"{msg}\"")
            print(f"      Expected: {expected_cat.value} (reply={expected_reply})")
            print(f"      Got:      {result.category.value} (reply={result.should_reply})")

    accuracy = (passed / total) * 100
    print(f"\n🎯 CLASSIFIER SCORE: {passed}/{total} Passed ({accuracy:.1f}% Accuracy)\n")
    return passed == total

def run_agent_end_to_end_tests():
    print("=" * 80)
    print("🧪 2. TESTING MASTER FARMERAGENT END-TO-END PIPELINE")
    print("=" * 80)

    agent = FarmerAgent()

    test_scenarios = [
        {
            "name": "Social Greeting Test",
            "message": "सुप्रभात जी 🙏",
            "sender": "Ramesh Patil",
            "expected_status": "IGNORED"
        },
        {
            "name": "Google Form Query Test",
            "message": "Sir weekly farm details ka google form link bhejiye",
            "sender": "Suresh Yadav",
            "expected_status": "FORM_HELP"
        },
        {
            "name": "Pest Query in Hinglish",
            "message": "Kapas me gulabi sundi ke liye kaun si dawai dale?",
            "sender": "Anil Kumar",
            "expected_status": "ANSWERED"
        },
        {
            "name": "Disease Query in Devanagari Hindi",
            "message": "गेहूं में पीली पत्तियां और पीला रतुआ का इलाज क्या है?",
            "sender": "Baldev Singh",
            "expected_status": "ANSWERED"
        },
        {
            "name": "Distress Signal Test",
            "message": "Sab fasal kharab ho gayi hai meri, ab mai suicide karunga",
            "sender": "Kisan Bhai",
            "expected_status": "ESCALATED"
        }
    ]

    all_scenarios_passed = True

    for idx, sc in enumerate(test_scenarios, 1):
        print(f"\nScenario [{idx}]: {sc['name']}")
        print(f"  Sender : {sc['sender']}")
        print(f"  Message: \"{sc['message']}\"")

        profile = FarmerProfile(name=sc["sender"], district="Nashik", crop="Cotton")
        resp = agent.process_message(sc["message"], sender_name=sc["sender"], profile=profile)

        print(f"  Status : {resp.status} (Category: {resp.category.value})")
        print(f"  Speed  : {resp.processing_time_ms} ms")

        if resp.status == sc["expected_status"]:
            print("  Result : ✅ CORRECT")
        else:
            print(f"  Result : ❌ FAILED (Expected {sc['expected_status']}, got {resp.status})")
            all_scenarios_passed = False

        if resp.reply_text:
            print("  --- Bot Reply Preview ---")
            for line in resp.reply_text.splitlines()[:5]:
                print(f"  {line}")
            print("  -------------------------")
        else:
            print("  --- Bot Action: Silently Ignored (Zero Group Spam) ---")

    print("\n" + "=" * 80)
    print(f"🎯 END-TO-END PIPELINE RESULT: {'✅ ALL TESTS PASSED' if all_scenarios_passed else '❌ SOME TESTS FAILED'}")
    print("=" * 80)
    return all_scenarios_passed

def main():
    c_ok = run_classifier_tests()
    a_ok = run_agent_end_to_end_tests()
    success = c_ok and a_ok
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
