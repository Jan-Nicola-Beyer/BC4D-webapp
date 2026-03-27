"""Embedding-first qualitative analysis pipeline.

Architecture:
  1. Embed all responses via nomic-embed-text (local, free)
  2. HDBSCAN clustering — discovers natural cluster count
  3. UMAP projection for 2D visualization
  4. LLM names clusters from representative responses
  5. LLM classifies noise/edge cases only

This replaces the previous two-pass LLM-only approach.
"""

from __future__ import annotations
import logging
from typing import Dict, List, Tuple, Optional

import numpy as np

log = logging.getLogger("bc4d_intel.core.embedder")


def embed_responses(responses: List[str], progress_cb=None) -> np.ndarray:
    """Embed all responses via nomic-embed-text (local Ollama, free).

    Returns (n_responses, 768) numpy array.
    """
    import ollama

    if progress_cb:
        progress_cb(f"Embedding {len(responses)} responses (local, free)...")

    # Batch embedding — Ollama handles batching internally
    vectors = []
    batch_size = 50
    for i in range(0, len(responses), batch_size):
        batch = responses[i:i + batch_size]
        # Prepend search prefix for nomic
        texts = [f"search_document: {r}" for r in batch]
        result = ollama.embed(model="nomic-embed-text", input=texts)
        vectors.extend(result["embeddings"])

        if progress_cb and (i + batch_size) % 100 == 0:
            progress_cb(f"Embedded {min(i + batch_size, len(responses))}/{len(responses)}")

    return np.array(vectors, dtype=np.float32)


def cluster_responses(
    embeddings: np.ndarray,
    min_cluster_size: int = 5,
    min_samples: int = 3,
) -> Tuple[np.ndarray, int]:
    """Run HDBSCAN on embeddings to find natural clusters.

    Returns:
        labels: array of cluster labels (-1 = noise/outlier)
        n_clusters: number of clusters found (excluding noise)
    """
    import hdbscan

    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric="euclidean",
        cluster_selection_method="eom",
    )
    labels = clusterer.fit_predict(embeddings)
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)

    log.info("HDBSCAN: %d clusters found, %d noise points",
             n_clusters, (labels == -1).sum())
    return labels, n_clusters


def project_umap(embeddings: np.ndarray) -> np.ndarray:
    """Project embeddings to 2D via UMAP for visualization.

    Returns (n_responses, 2) array of x, y coordinates.
    """
    import umap

    reducer = umap.UMAP(
        n_components=2,
        n_neighbors=15,
        min_dist=0.1,
        metric="cosine",
        random_state=42,
    )
    coords = reducer.fit_transform(embeddings)
    return coords.astype(np.float32)


def get_representative_responses(
    responses: List[str],
    embeddings: np.ndarray,
    labels: np.ndarray,
    cluster_id: int,
    n: int = 10,
) -> List[str]:
    """Get the N most central responses for a cluster.

    Central = closest to the cluster centroid in embedding space.
    These are the most representative examples for naming.
    """
    mask = labels == cluster_id
    cluster_indices = np.where(mask)[0]
    cluster_vecs = embeddings[mask]

    if len(cluster_vecs) == 0:
        return []

    # Centroid
    centroid = cluster_vecs.mean(axis=0)

    # Distance to centroid
    dists = np.linalg.norm(cluster_vecs - centroid, axis=1)
    sorted_idx = np.argsort(dists)

    # Return the n closest responses (most representative)
    result = []
    for i in sorted_idx[:n]:
        original_idx = cluster_indices[i]
        result.append(responses[original_idx])
    return result


def full_pipeline(
    responses: List[str],
    api_key: str,
    min_cluster_size: int = 5,
    progress_cb=None,
) -> Dict:
    """Run the complete embedding-first pipeline.

    Returns:
        embeddings: (n, 768) array
        labels: cluster assignment per response (-1 = noise)
        umap_coords: (n, 2) array for visualization
        taxonomy: [{id, title, description, coding_rule, count}]
        classifications: [{text, cluster_id, confidence}]
    """
    n = len(responses)

    # Step 1: Embed (free, local)
    if progress_cb:
        progress_cb(f"Step 1/4: Embedding {n} responses (free, local)...")
    embeddings = embed_responses(responses, progress_cb)

    # Step 2: Cluster (free, local)
    if progress_cb:
        progress_cb("Step 2/4: Discovering clusters (HDBSCAN)...")
    # Adjust min_cluster_size based on dataset size
    mcs = max(3, min(min_cluster_size, n // 10))
    labels, n_clusters = cluster_responses(embeddings, min_cluster_size=mcs, min_samples=max(2, mcs - 1))

    # Step 3: UMAP projection (free, local)
    if progress_cb:
        progress_cb("Step 3/4: Projecting to 2D (UMAP)...")
    umap_coords = project_umap(embeddings)

    # Step 4: Name clusters via LLM (Sonnet, ~$0.01 per cluster)
    if progress_cb:
        progress_cb(f"Step 4/4: Naming {n_clusters} clusters via AI...")

    from bc4d_intel.ai.claude_client import call_claude

    taxonomy = []
    for cid in range(n_clusters):
        reps = get_representative_responses(responses, embeddings, labels, cid, n=10)
        count = int((labels == cid).sum())

        if not reps:
            continue

        # Send representative responses to Sonnet for naming
        reps_text = "\n".join(f"- {r[:300]}" for r in reps)
        prompt = (
            f"Diese {count} Antworten wurden automatisch als thematisch aehnlich gruppiert. "
            f"Hier sind die {len(reps)} repraesentativsten:\n\n{reps_text}\n\n"
            f"Erstelle:\n"
            f"1. Einen praegnanten deutschen Cluster-Titel (3-6 Woerter)\n"
            f"2. Eine kurze Beschreibung (1 Satz)\n"
            f"3. Eine Kodierregel: 'Einschliessen: Antworten die X erwaehnen. "
            f"Ausschliessen: Antworten die Y erwaehnen.'\n\n"
            f"Antworte als JSON: {{\"title\": \"...\", \"description\": \"...\", \"coding_rule\": \"...\"}}"
        )

        try:
            import json, re
            resp = call_claude(
                system="Du bist ein*e qualitative*r Forschungsassistent*in. Antworte nur mit JSON.",
                user_msg=prompt,
                task="tagging",  # cheaper model OK for naming
                api_key=api_key,
                max_tokens=300,
            )
            m = re.search(r'\{.*\}', resp, re.DOTALL)
            if m:
                parsed = json.loads(m.group())
                taxonomy.append({
                    "id": f"cluster_{cid}",
                    "title": parsed.get("title", f"Cluster {cid + 1}"),
                    "description": parsed.get("description", ""),
                    "coding_rule": parsed.get("coding_rule", ""),
                    "count": count,
                })
            else:
                taxonomy.append({
                    "id": f"cluster_{cid}", "title": f"Cluster {cid + 1}",
                    "description": "", "coding_rule": "", "count": count,
                })
        except Exception as e:
            log.warning("Cluster naming failed for %d: %s", cid, e)
            taxonomy.append({
                "id": f"cluster_{cid}", "title": f"Cluster {cid + 1}",
                "description": str(e), "coding_rule": "", "count": count,
            })

    # Handle noise cluster
    n_noise = int((labels == -1).sum())
    if n_noise > 0:
        taxonomy.append({
            "id": "noise",
            "title": "Sonstige / Nicht zuordenbar",
            "description": f"{n_noise} Antworten, die keinem klaren Thema zugeordnet werden konnten.",
            "coding_rule": "Sehr kurze, mehrdeutige oder einzigartige Antworten.",
            "count": n_noise,
        })

    # Build classifications
    classifications = []
    for i, (text, label) in enumerate(zip(responses, labels)):
        if label == -1:
            cid = "noise"
            conf = "low"
        else:
            cid = f"cluster_{label}"
            # Confidence based on distance to centroid
            mask = labels == label
            cluster_vecs = embeddings[mask]
            centroid = cluster_vecs.mean(axis=0)
            dist = float(np.linalg.norm(embeddings[i] - centroid))
            median_dist = float(np.median(np.linalg.norm(cluster_vecs - centroid, axis=1)))
            if dist < median_dist * 0.7:
                conf = "high"
            elif dist < median_dist * 1.3:
                conf = "medium"
            else:
                conf = "low"

        classifications.append({
            "text": text,
            "cluster_id": cid,
            "confidence": conf,
            "human_override": "",
        })

    if progress_cb:
        progress_cb(f"Done: {n_clusters} clusters from {n} responses")

    return {
        "embeddings": embeddings,
        "labels": labels,
        "umap_coords": umap_coords,
        "taxonomy": taxonomy,
        "classifications": classifications,
    }
