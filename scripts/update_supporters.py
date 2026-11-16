import json
import os


def update_supporters():
    json_path = 'data/supporters.json'
    if not os.path.exists(json_path):
        print(f"Error: {json_path} not found.")
        return

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    special_thanks = data.get('specialThanks', [])
    all_supporters = data.get('allSupporters', [])
    total_count = data.get('totalCount', len(all_supporters))

    lines = [
        '# Supporter Recognition',
        '',
        'Thank you to everyone who supports the development of ComfyUI LoRA Manager.',
        '',
        '## Special Thanks',
        '',
    ]

    if special_thanks:
        lines.extend([', '.join(f'**{name}**' for name in special_thanks), ''])
    else:
        lines.extend(['*None yet*', ''])

    lines.extend([f'## Supporters ({total_count})', ''])
    if all_supporters:
        lines.extend([
            '<details>',
            '<summary>View all supporters</summary>',
            '',
            ', '.join(all_supporters),
            '',
            '</details>',
            '',
        ])
    else:
        lines.extend(['*No supporters listed yet*', ''])

    output_path = 'SUPPORTERS.md'
    with open(output_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines))

    print(f"Successfully updated {output_path} with {len(all_supporters)} supporters!")


if __name__ == '__main__':
    update_supporters()
