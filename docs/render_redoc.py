import html
import json
from argparse import ArgumentParser, Namespace
from pathlib import Path


def parse_args() -> Namespace:
    parser = ArgumentParser()
    parser.add_argument("--spec", required=True)
    parser.add_argument("--template", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    spec_path = Path(args.spec)
    if spec_path.stat().st_size == 0:
        raise SystemExit("openapi.json is empty")

    with spec_path.open(encoding="utf-8") as spec_file:
        spec = json.load(spec_file)

    template_path = Path(args.template)
    template = template_path.read_text(encoding="utf-8")
    if "{{TITLE}}" not in template:
        raise SystemExit("template is missing the {{TITLE}} placeholder")

    raw_title = spec.get("info", {}).get("title")
    if not isinstance(raw_title, str) or not raw_title.strip():
        raw_title = "API Documentation"

    title = html.escape(raw_title)
    output = template.replace("{{TITLE}}", title)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output, encoding="utf-8")


if __name__ == "__main__":
    main()
