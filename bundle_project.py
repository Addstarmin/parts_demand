import os
import sys

# 集約対象外にするフォルダやファイル
IGNORE_DIRS = {
    "node_modules", "dist", "build", ".git", ".venv", "venv", 
    "__pycache__", ".vscode", ".idea", "dist-ssr"
}
IGNORE_FILES = {
    ".DS_Store", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", 
    "*.pyc", "*.png", "*.jpg", "*.jpeg", "*.gif", "*.ico", "*.svg"
}

def should_ignore(name, ignore_set):
    """無視パターンに合致するか判定"""
    if name in ignore_set:
        return True
    for ignore_item in ignore_set:
        if ignore_item.startswith("*.") and name.endswith(ignore_item[1:]):
            return True
    return False

def detect_run_commands(root_dir):
    """
    フォルダ構造を解析し、最適な実行方法を自動で推測・生成する関数
    """
    commands = []
    
    # 探索用フラグ
    has_fastapi = False
    has_python_main = False
    python_main_path = ""
    has_node = False
    node_path = ""
    node_scripts = []

    # フォルダ内を一通り走査して手がかりを探す
    for current_root, dirs, files in os.walk(root_dir):
        # 無視するディレクトリはスキップ
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        
        # 相対パスを取得
        rel_path = os.path.relpath(current_root, root_dir)
        if rel_path == ".":
            rel_path = ""

        # 1. Python系の判定
        if "main.py" in files:
            has_python_main = True
            python_main_path = os.path.join(rel_path, "main.py")
            
            # main.py の中身を少し読んで FastAPI かどうか調べる
            try:
                with open(os.path.join(current_root, "main.py"), "r", encoding="utf-8") as f:
                    content = f.read()
                    if "FastAPI" in content or "uvicorn" in content:
                        has_fastapi = True
            except:
                pass

        # 2. Node.js (フロントエンドなど) の判定
        if "package.json" in files:
            has_node = True
            node_path = rel_path
            
            # package.json の scripts から起動コマンドを読み取る
            try:
                import json
                with open(os.path.join(current_root, "package.json"), "r", encoding="utf-8") as f:
                    pkg = json.load(f)
                    scripts = pkg.get("scripts", {})
                    if "dev" in scripts:
                        node_scripts.append("npm run dev")
                    elif "start" in scripts:
                        node_scripts.append("npm start")
            except:
                node_scripts.append("npm run dev (推測)")

    # --- 検出した情報から「実行方法説明テキスト」を自動生成 ---
    commands.append("===================================================")
    commands.append("🚀 AIによるプロジェクト起動・実行方法の自動推測")
    commands.append("===================================================")

    # バックエンド（Python）の起動コマンド推測
    if has_python_main:
        commands.append("【バックエンド / Python スクリプト】")
        base_dir = os.path.dirname(python_main_path)
        file_name = os.path.basename(python_main_path)
        
        if base_dir:
            commands.append(f"cd ~/{base_dir}")
        else:
            commands.append("cd ~/[プロジェクトのルート]")
            
        if has_fastapi:
            commands.append(f"python3 {file_name}  # FastAPI/Uvicorn サーバーの起動")
        else:
            commands.append(f"python3 {file_name}  # スクリプトの実行")
        commands.append("")

    # フロントエンド（Node.js / Reactなど）の起動コマンド推測
    if has_node:
        commands.append("【フロントエンド / Node.js 環境 (別ターミナルで起動)】")
        if node_path:
            commands.append(f"cd ~/{node_path}")
        else:
            commands.append("cd ~/[プロジェクトのルート]")
            
        for script in node_scripts:
            commands.append(f"{script}  # 開発サーバーの起動")
        commands.append("")

    if not has_python_main and not has_node:
        commands.append("※ 明確なWebサーバーやスクリプトの起動ファイル（main.py, package.json等）が検出されませんでした。")
        commands.append("通常のソースコード閲覧用として集約しています。")

    commands.append("===================================================\n\n")
    return "\n".join(commands)


def bundle_project(root_dir, output_file_path):
    print(f"📦 プロジェクトの解析を開始: {root_dir}")
    
    with open(output_file_path, "w", encoding="utf-8") as out_f:
        
        # 【自動生成機能】構成からコマンドを推測して先頭に書き込む
        run_instructions = detect_run_commands(root_dir)
        out_f.write(run_instructions)
        
        # 各ファイルの集約処理（行番号付き）
        for current_root, dirs, files in os.walk(root_dir):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            
            for file in sorted(files):
                if should_ignore(file, IGNORE_FILES):
                    continue
                
                full_path = os.path.join(current_root, file)
                if os.path.abspath(full_path) == os.path.abspath(output_file_path):
                    continue
                
                out_f.write(f"ファイル名: {full_path}\n")
                out_f.write("```コードの内容```\n")
                
                try:
                    with open(full_path, "r", encoding="utf-8") as in_f:
                        lines = in_f.read().splitlines()
                        for i, line in enumerate(lines, start=1):
                            out_f.write(f"{i}: {line}\n")
                except UnicodeDecodeError:
                    out_f.write("[バイナリファイルのためテキスト出力をスキップします]\n")
                except Exception as e:
                    out_f.write(f"[ファイルの読み込みエラー: {str(e)}]\n")
                
                out_f.write("\n\n\n")
                
    print(f"✨ 集約完了! 出力先: {output_file_path}")

if __name__ == "__main__":
    target_directory = os.getcwd()
    output_filename = "project_summary_code.txt"
    output_path = os.path.join(target_directory, output_filename)
    
    bundle_project(target_directory, output_path)
