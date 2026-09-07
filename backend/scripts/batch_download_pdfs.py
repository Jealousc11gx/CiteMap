"""批量下载已入库 arXiv 论文的 PDF。"""
import json
import time
import urllib.request


def main():
    with urllib.request.urlopen("http://localhost:8000/api/papers") as resp:
        papers = json.loads(resp.read().decode())

    arxiv_without_pdf = [p for p in papers if p.get("source") == "arxiv" and not p.get("pdf_path")]
    print(f"Total papers: {len(papers)}")
    print(f"Arxiv papers without PDF: {len(arxiv_without_pdf)}")

    success = 0
    failed = 0
    for i, p in enumerate(arxiv_without_pdf, 1):
        paper_id = p["id"]
        title = p.get("title", "")[:60]
        print(f"[{i}/{len(arxiv_without_pdf)}] Downloading PDF for {paper_id} - {title}...")
        try:
            req = urllib.request.Request(
                f"http://localhost:8000/api/papers/{paper_id}/download-pdf",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode())
                print(f"  -> {result.get('status', 'unknown')}: {result.get('pdf_path', '')}")
                success += 1
        except Exception as e:
            print(f"  -> ERROR: {e}")
            failed += 1
        if i < len(arxiv_without_pdf):
            time.sleep(2)

    print(f"Batch download complete. Success: {success}, Failed: {failed}")


if __name__ == "__main__":
    main()
