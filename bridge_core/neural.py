#!/usr/bin/env python3
"""
CHAOS TYPE ZERO Neural Network — On-device inference and ML
No heavy dependencies — TF-IDF, cosine similarity, n-gram analysis
"""

import re
import math
import json
import hashlib
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

CTZ_ROOT = Path(__file__).parent.parent
DATA_DIR = CTZ_ROOT / "data" / "neural"


def _tokenize(text: str) -> list:
    return re.findall(r'\b\w+\b', text.lower())


def _ngrams(tokens: list, n: int) -> list:
    return [tuple(tokens[i:i+n]) for i in range(len(tokens) - n + 1)]


def _cosine_sim(v1: list, v2: list) -> float:
    if len(v1) != len(v2) or not v1:
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    mag1 = math.sqrt(sum(a * a for a in v1))
    mag2 = math.sqrt(sum(b * b for b in v2))
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot / (mag1 * mag2)


# ── Sentiment lexicon ───────────────────────────────────────────────────

_POSITIVE = {
    "good", "great", "excellent", "amazing", "wonderful", "fantastic",
    "awesome", "love", "happy", "best", "beautiful", "brilliant",
    "perfect", "nice", "fine", "pleasant", "delightful", "superb",
    "outstanding", "magnificent", "terrific", "fabulous", "impressive",
    "remarkable", "exceptional", "splendid", "marvelous", "glorious",
    "enjoy", "pleased", "glad", "thrilled", "excited", "grateful",
    "thankful", "appreciate", "adore", "favor", "win", "success",
    "triumph", "victory", "accomplish", "achieve", "progress",
}

_NEGATIVE = {
    "bad", "terrible", "awful", "horrible", "worst", "hate", "ugly",
    "stupid", "dumb", "annoying", "boring", "disgusting", "pathetic",
    "dreadful", "miserable", "painful", "disappointing", "failure",
    "broken", "wrong", "error", "fail", "crash", "dead", "lost",
    "angry", "sad", "depressed", "frustrated", "disappointed", "upset",
    "unhappy", "regret", "unfortunately", "suffer", "problem", "issue",
    "defect", "flaw", "weak", "poor", "inferior", "lousy", "trash",
}

_INTENSIFIERS = {
    "very", "extremely", "incredibly", "absolutely", "totally",
    "completely", "utterly", "really", "highly", "deeply",
}

_NEGATORS = {
    "not", "no", "never", "neither", "nobody", "nothing",
    "nowhere", "nor", "cannot", "can't", "don't", "won't",
    "isn't", "aren't", "wasn't", "weren't", "doesn't", "didn't",
}

# ── Topic keywords ──────────────────────────────────────────────────────

_TOPIC_KEYWORDS = {
    "technology": {
        "computer", "software", "hardware", "code", "programming", "ai",
        "data", "server", "network", "database", "api", "algorithm",
        "machine", "learning", "digital", "system", "internet", "cloud",
        "cyber", "tech", "robot", "automat", "encrypt", "firewall",
        "blockchain", "quantum", "neural", "deep", "model",
    },
    "science": {
        "research", "experiment", "hypothesis", "theory", "laboratory",
        "physics", "chemistry", "biology", "atom", "molecule", "cell",
        "genome", "evolution", "energy", "quantum", "spectrum", "magnetic",
        "gravity", "radiation", "compound", "element", "reaction",
    },
    "business": {
        "market", "revenue", "profit", "customer", "sales", "strategy",
        "management", "finance", "investment", "budget", "growth",
        "company", "startup", "entrepreneur", "brand", "marketing",
        "product", "service", "trade", "economy", "stock", "capital",
    },
    "health": {
        "medical", "doctor", "patient", "treatment", "disease", "health",
        "hospital", "medicine", "symptom", "diagnosis", "therapy", "surgery",
        "clinical", "pharmaceutical", "mental", "physical", "immune",
        "nutrition", "exercise", "wellness", "vaccine", "infection",
    },
    "politics": {
        "government", "election", "president", "policy", "law", "vote",
        "congress", "democrat", "republican", "political", "campaign",
        "legislation", "regulation", "diplomacy", "sanctions", "cabinet",
    },
    "sports": {
        "team", "player", "game", "match", "score", "championship",
        "tournament", "coach", "athlete", "league", "stadium", "goal",
        "win", "defeat", "season", "draft", "medal", "record", "run",
    },
    "arts": {
        "music", "painting", "film", "art", "creative", "design",
        "theater", "dance", "literature", "poetry", "sculpture",
        "photography", "fashion", "architecture", "museum", "gallery",
    },
}

# ── Intent patterns ─────────────────────────────────────────────────────

_INTENT_PATTERNS = [
    (r'\b(what|how|when|where|who|which|why)\b.*\?', "question"),
    (r'\b(please|can you|could you|would you|help me)\b', "request"),
    (r'\b(don\'t|do not|stop|quit|exit|cancel)\b', "negative_command"),
    (r'\b(start|run|execute|launch|begin|open)\b', "start_command"),
    (r'\b(stop|halt|pause|suspend|terminate|close)\b', "stop_command"),
    (r'\b(search|find|look|query|check|verify)\b', "search_command"),
    (r'\b(create|make|build|generate|new|add)\b', "create_command"),
    (r'\b(delete|remove|destroy|erase|drop)\b', "delete_command"),
    (r'\b(update|modify|change|edit|set|configure)\b', "update_command"),
    (r'\b(show|display|list|print|view|display)\b', "display_command"),
    (r'\b(thank|thanks|appreciate)\b', "acknowledgment"),
    (r'\b(hello|hi|hey|greetings|sup)\b', "greeting"),
    (r'\b(bye|goodbye|see you|later|farewell)\b', "farewell"),
]

# ── Common entity patterns ──────────────────────────────────────────────

_ENTITY_PATTERNS = [
    ("email", r'\b[\w.+-]+@[\w-]+\.[\w.]+\b'),
    ("url", r'https?://\S+'),
    ("phone", r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b'),
    ("date", r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b'),
    ("time", r'\b\d{1,2}:\d{2}(?:\s?[ap]m)?\b'),
    ("number", r'\b\d+(?:\.\d+)?\b'),
    ("quoted", r'"([^"]+)"'),
    ("quoted2", r"'([^']+)'"),
]

# ── Language detection char ranges ──────────────────────────────────────

_LANG_RANGES = [
    ("ja", range(0x3040, 0x309F + 1)),
    ("ko", range(0xAC00, 0xD7AF + 1)),
    ("zh", range(0x4E00, 0x9FFF + 1)),
    ("ar", range(0x0600, 0x06FF + 1)),
    ("ru", range(0x0400, 0x04FF + 1)),
]


class CTZNeural:
    """CHAOS TYPE ZERO Neural Network — lightweight on-device inference"""

    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._idf_cache = {}
        self._db_path = str(DATA_DIR / "neural.db")
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS classifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text_hash TEXT,
                category TEXT,
                confidence REAL,
                created_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS command_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT,
                intent TEXT,
                entities TEXT,
                created_at TEXT
            )
        """)
        conn.commit()
        conn.close()

    # ── Classification ──────────────────────────────────────────────────

    def classify(self, text: str) -> dict:
        tokens = set(_tokenize(text))

        scores = {}
        for topic, keywords in _TOPIC_KEYWORDS.items():
            overlap = len(tokens & keywords)
            total = len(tokens) if tokens else 1
            scores[topic] = overlap / total

        # Sentiment
        pos = len(tokens & _POSITIVE)
        neg = len(tokens & _NEGATIVE)
        total_sent = pos + neg if (pos + neg) > 0 else 1

        intensifier_boost = len(tokens & _INTENSIFIERS) * 0.15
        negator_flip = len(tokens & _NEGATORS) > 0

        raw_sentiment = (pos - neg) / total_sent
        if negator_flip:
            raw_sentiment *= -1
        raw_sentiment = max(-1.0, min(1.0, raw_sentiment + intensifier_boost))

        if raw_sentiment > 0.1:
            sentiment = "positive"
        elif raw_sentiment < -0.1:
            sentiment = "negative"
        else:
            sentiment = "neutral"

        best_topic = max(scores, key=scores.get) if scores else "general"
        topic_conf = scores.get(best_topic, 0.0)
        confidence = min(0.95, max(0.1, 0.3 + topic_conf + abs(raw_sentiment) * 0.3))

        result = {
            "category": best_topic,
            "confidence": round(confidence, 3),
            "sentiment": sentiment,
            "sentiment_score": round(raw_sentiment, 3),
            "topic_scores": {k: round(v, 3) for k, v in sorted(scores.items(), key=lambda x: -x[1])[:5]},
        }

        text_hash = hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()[:12]
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                "INSERT INTO classifications (text_hash, category, confidence, created_at) VALUES (?, ?, ?, ?)",
                (text_hash, best_topic, confidence, datetime.now().isoformat()),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

        return result

    # ── Summarization (extractive) ──────────────────────────────────────

    def summarize(self, text: str, max_sentences: int = 3) -> str:
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        if not sentences:
            return text

        if len(sentences) <= max_sentences:
            return " ".join(sentences)

        word_freq = Counter(_tokenize(text))

        scored = []
        for i, sent in enumerate(sentences):
            sent_tokens = _tokenize(sent)
            if not sent_tokens:
                scored.append((i, 0.0, sent))
                continue

            freq_score = sum(word_freq.get(w, 0) for w in sent_tokens) / len(sent_tokens)
            position_score = 1.0 / (1.0 + i)
            length_score = min(1.0, len(sent_tokens) / 20)

            combined = freq_score * 0.5 + position_score * 0.3 + length_score * 0.2
            scored.append((i, combined, sent))

        scored.sort(key=lambda x: -x[1])
        top = sorted(scored[:max_sentences], key=lambda x: x[0])

        return " ".join(s[2] for s in top)

    # ── Embedding (TF-IDF based) ────────────────────────────────────────

    def _compute_idf(self, corpus: list) -> dict:
        corpus_id = hashlib.md5(json.dumps(corpus, sort_keys=True).encode(), usedforsecurity=False).hexdigest()[:8]
        if corpus_id in self._idf_cache:
            return self._idf_cache[corpus_id]

        n_docs = len(corpus)
        df = Counter()
        for doc in corpus:
            tokens = set(_tokenize(doc))
            for t in tokens:
                df[t] += 1

        idf = {}
        for term, freq in df.items():
            idf[term] = math.log((1 + n_docs) / (1 + freq)) + 1

        self._idf_cache[corpus_id] = idf
        return idf

    def embed(self, text: str) -> list:
        tokens = _tokenize(text)
        if not tokens:
            return []

        vocab = sorted(set(tokens))
        tf = Counter(tokens)

        embedding = []
        for word in vocab:
            term_tf = tf[word] / len(tokens)
            doc_freq_sum = sum(1 for w in tokens if w == word)
            idf_val = math.log(2) + 1
            embedding.append(round(term_tf * idf_val, 6))

        return embedding

    def embed_with_corpus(self, text: str, corpus: list) -> list:
        tokens = _tokenize(text)
        if not tokens:
            return []

        idf = self._compute_idf(corpus)
        vocab = sorted(idf.keys())
        tf = Counter(tokens)

        embedding = []
        for word in vocab:
            term_tf = tf.get(word, 0) / len(tokens)
            idf_val = idf.get(word, math.log(2) + 1)
            embedding.append(round(term_tf * idf_val, 6))

        return embedding

    # ── Similarity ──────────────────────────────────────────────────────

    def similarity(self, text1: str, text2: str) -> float:
        tokens1 = _tokenize(text1)
        tokens2 = _tokenize(text2)

        if not tokens1 or not tokens2:
            return 0.0

        vocab = sorted(set(tokens1 + tokens2))
        tf1 = Counter(tokens1)
        tf2 = Counter(tokens2)

        v1 = [tf1.get(w, 0) / len(tokens1) for w in vocab]
        v2 = [tf2.get(w, 0) / len(tokens2) for w in vocab]

        cos_sim = _cosine_sim(v1, v2)

        bigrams1 = set(_ngrams(tokens1, 2))
        bigrams2 = set(_ngrams(tokens2, 2))
        if bigrams1 or bigrams2:
            bigram_jaccard = len(bigrams1 & bigrams2) / max(len(bigrams1 | bigrams2), 1)
        else:
            bigram_jaccard = 0.0

        return round(cos_sim * 0.7 + bigram_jaccard * 0.3, 4)

    # ── Pattern Detection ───────────────────────────────────────────────

    def detect_patterns(self, texts: list) -> list:
        if not texts:
            return []

        patterns = []
        all_tokens_list = [_tokenize(t) for t in texts]
        word_counts = Counter()
        bigram_counts = Counter()

        for tokens in all_tokens_list:
            word_counts.update(tokens)
            bigram_counts.update(_ngrams(tokens, 2))

        n = len(texts)

        # Frequent words appearing in >30% of texts
        min_doc_freq = max(1, n * 0.3)
        for word, count in word_counts.most_common(50):
            if count >= min_doc_freq:
                patterns.append({
                    "type": "frequent_word",
                    "pattern": word,
                    "frequency": count,
                    "doc_ratio": round(count / n, 3),
                })

        # Common bigrams
        min_bigram_freq = max(1, n * 0.2)
        for bigram, count in bigram_counts.most_common(30):
            if count >= min_bigram_freq:
                patterns.append({
                    "type": "common_bigram",
                    "pattern": " ".join(bigram),
                    "frequency": count,
                    "doc_ratio": round(count / n, 3),
                })

        # Length pattern
        lengths = [len(t) for t in texts]
        avg_len = sum(lengths) / len(lengths)
        std_len = math.sqrt(sum((l - avg_len) ** 2 for l in lengths) / len(lengths))
        patterns.append({
            "type": "length_stats",
            "avg_length": round(avg_len, 1),
            "std_length": round(std_len, 1),
            "min_length": min(lengths),
            "max_length": max(lengths),
        })

        # Character distribution consistency
        char_counts = [Counter(t.lower()) for t in texts]
        common_chars = set.intersection(*[set(c.keys()) for c in char_counts]) if char_counts else set()
        if common_chars:
            patterns.append({
                "type": "shared_characters",
                "characters": sorted(common_chars)[:20],
                "count": len(common_chars),
            })

        return patterns

    # ── Batch Categorization ────────────────────────────────────────────

    def categorize_batch(self, texts: list) -> dict:
        categories = defaultdict(list)

        for text in texts:
            result = self.classify(text)
            cat = result["category"]
            categories[cat].append({
                "text": text[:100],
                "confidence": result["confidence"],
                "sentiment": result["sentiment"],
            })

        summary = {}
        for cat, items in categories.items():
            avg_conf = sum(i["confidence"] for i in items) / len(items)
            summary[cat] = {
                "count": len(items),
                "avg_confidence": round(avg_conf, 3),
                "items": items[:5],
            }

        return dict(sorted(summary.items(), key=lambda x: -x[1]["count"]))

    # ── Utility ─────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        return {
            "module": "CTZNeural",
            "data_dir": str(DATA_DIR),
            "idf_cache_size": len(self._idf_cache),
            "features": [
                "classify", "summarize", "embed", "similarity",
                "detect_patterns", "categorize_batch",
            ],
        }


# Singleton
_neural = None


def get_neural() -> CTZNeural:
    global _neural
    if _neural is None:
        _neural = CTZNeural()
    return _neural


if __name__ == "__main__":
    nn = get_neural()
    print("=== CHAOS TYPE ZERO Neural Network ===")
    print(f"Status: {json.dumps(nn.get_status(), indent=2)}")

    print("\n--- Classification ---")
    print(json.dumps(nn.classify("The AI software crashed the server and lost all data"), indent=2))
    print(json.dumps(nn.classify("Amazing breakthrough in quantum computing research!"), indent=2))

    print("\n--- Summarization ---")
    long_text = (
        "Artificial intelligence is transforming industries worldwide. "
        "Machine learning algorithms can now process vast amounts of data efficiently. "
        "Companies are investing billions in AI research and development. "
        "The future of technology depends on responsible AI deployment. "
        "Ethical considerations must guide AI advancement."
    )
    print(nn.summarize(long_text))

    print("\n--- Similarity ---")
    print(f"The cat sat on the mat vs A cat sitting on a mat: {nn.similarity('The cat sat on the mat', 'A cat sitting on a mat')}")
    print(f"The cat sat on the mat vs Quantum physics is fascinating: {nn.similarity('The cat sat on the mat', 'Quantum physics is fascinating')}")

    print("\n--- Pattern Detection ---")
    texts = [
        "Machine learning is great for data analysis",
        "Deep learning models process data well",
        "AI and machine learning transform data science",
    ]
    patterns = nn.detect_patterns(texts)
    for p in patterns[:5]:
        print(f"  {p['type']}: {p.get('pattern', p.get('avg_length', ''))} (freq={p.get('frequency', '-')})")

    print("\n--- Batch Categorization ---")
    batch = [
        "New smartphone features amazing camera",
        "Stock market reaches all-time high",
        "Patient recovers after surgery",
        "Team wins championship game",
    ]
    print(json.dumps(nn.categorize_batch(batch), indent=2))
