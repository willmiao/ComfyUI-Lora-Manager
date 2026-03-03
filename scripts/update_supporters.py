import json
import os
import re

def update_readme():
    # 1. Read JSON data
    json_path = 'data/supporters.json'
    if not os.path.exists(json_path):
        print(f"Error: {json_path} not found.")
        return

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 2. Generate Markdown content
    special_thanks = data.get('specialThanks', [])
    all_supporters = data.get('allSupporters', [])
    total_count = data.get('totalCount', len(all_supporters))
    
    md_content = "\n### 🌟 Special Thanks\n\n"
    if special_thanks:
        md_content += ", ".join([f"**{name}**" for name in special_thanks]) + "\n\n"
    else:
        md_content += "*None yet*\n\n"
    
    md_content += f"### 💖 Supporters ({total_count})\n\n"
    if all_supporters:
        # Using a details block for the long list of supporters
        md_content += "<details>\n<summary>Click to view all awesome supporters</summary>\n<br>\n\n"
        md_content += ", ".join(all_supporters)
        md_content += "\n\n</details>\n"
    else:
        md_content += "*No supporters listed yet*\n"

    # 3. Read existing README.md
    readme_path = 'README.md'
    with open(readme_path, 'r', encoding='utf-8') as f:
        readme = f.read()

    # 4. Replace content between placeholders
    start_tag = '<!-- SUPPORTERS-START -->'
    end_tag = '<!-- SUPPORTERS-END -->'
    
    if start_tag not in readme or end_tag not in readme:
        print(f"Error: Placeholders {start_tag} and {end_tag} not found in {readme_path}")
        return

    # Using non-regex replacement to avoid issues with special characters in names
    parts = readme.split(start_tag)
    before_start = parts[0]
    after_start = parts[1].split(end_tag)
    after_end = after_start[1]
    
    new_readme = f"{before_start}{start_tag}\n{md_content}\n{end_tag}{after_end}"

    # 5. Write back to README.md
    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(new_readme)
        
    print(f"Successfully updated {readme_path} with {len(all_supporters)} supporters!")

if __name__ == '__main__':
    update_readme()
