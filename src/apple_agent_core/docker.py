"""Docker コンテナ管理モジュール。

セッションごとに常駐 Docker コンテナを起動し、ツール実行のみをコンテナ内に隔離する。
エージェントループはホスト側で動作し、ツール実行時のみ ``docker exec`` 経由でコンテナに委譲する。
"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

#: コンテナ内実行を示す環境変数名。Dockerfile の ENV でも設定される。
CONTAINER_FLAG_ENV = "APPLE_AGENT_CONTAINER"

#: Docker をスキップして直接実行するフラグ（開発・テスト用）。
SKIP_DOCKER_ENV = "APPLE_AGENT_SKIP_DOCKER"

#: 使用する Docker イメージ名の環境変数名。
IMAGE_ENV = "AGENT_DOCKER_IMAGE"

#: デフォルトの Docker イメージ名。
DEFAULT_IMAGE = "apple-agent-core:latest"

#: コンテナ内のワークスペースマウントポイント。
CONTAINER_WORKSPACE = "/workspace"

#: docker exec ツール実行のタイムアウト（秒）。
EXEC_TIMEOUT = 120


def is_inside_container() -> bool:
    """Docker コンテナ内で実行中かどうかを返す。

    環境変数 ``APPLE_AGENT_CONTAINER=1`` またはコンテナ固有の
    ``/.dockerenv`` ファイルの存在で判定する。

    :return: コンテナ内で実行中の場合は ``True``。
    """
    if os.environ.get(CONTAINER_FLAG_ENV) == "1":
        return True
    return Path("/.dockerenv").exists()


def should_skip_docker() -> bool:
    """Docker の使用をスキップするかどうかを返す。

    ``APPLE_AGENT_SKIP_DOCKER=1`` 環境変数が設定されている場合に ``True`` を返す。
    開発・テスト用のバイパスフラグ。

    :return: Docker をスキップする場合は ``True``。
    """
    return os.environ.get(SKIP_DOCKER_ENV) == "1"


def get_image_name() -> str:
    """使用する Docker イメージ名を返す。

    環境変数 ``AGENT_DOCKER_IMAGE`` が設定されていればその値を、
    未設定の場合は :data:`DEFAULT_IMAGE` を返す。

    :return: Docker イメージ名。
    """
    return os.environ.get(IMAGE_ENV, DEFAULT_IMAGE)


def get_container_name(session_id: str) -> str:
    """セッション ID からコンテナ名を生成する。

    :param session_id: セッション ID。
    :return: ``agent-<session_id>`` 形式のコンテナ名。
    """
    return f"agent-{session_id}"


def ensure_image() -> bool:
    """Docker イメージの存在を確認し、なければ自動ビルドする。

    :return: イメージが利用可能な場合は ``True``、失敗した場合は ``False``。
    """
    name = get_image_name()

    result = subprocess.run(
        ["docker", "image", "inspect", name],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return True

    print(f"[docker] イメージ '{name}' が見つかりません。ビルドを開始します...")
    project_root = Path(__file__).parent.parent.parent
    dockerfile = project_root / "docker" / "Dockerfile"

    build_result = subprocess.run(
        ["docker", "build", "-t", name, "-f", str(dockerfile), str(project_root)],
    )
    if build_result.returncode != 0:
        print(
            f"[docker] ビルドに失敗しました。手動でビルドしてください: docker build -t {name} -f docker/Dockerfile .",
            file=sys.stderr,
        )
        return False

    print(f"[docker] イメージ '{name}' をビルドしました。")
    return True


def _is_container_running(container_name: str) -> bool:
    """指定したコンテナが実行中かどうかを確認する。

    :param container_name: 確認するコンテナ名。
    :return: コンテナが実行中の場合は ``True``。
    """
    result = subprocess.run(
        [
            "docker",
            "inspect",
            "--format",
            "{{.State.Running}}",
            container_name,
        ],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def start_session_container(session_id: str, workspace_base: Path) -> str:
    """セッション用の常駐 Docker コンテナをデタッチモードで起動する。

    コンテナは ``sleep infinity`` で常駐し、
    ``docker exec`` によるツール実行を受け付ける状態で待機する。

    :param session_id: セッション ID。
    :param workspace_base: ホスト側のワークスペースベースディレクトリ。
    :return: 起動したコンテナの名前。
    :raises RuntimeError: コンテナの起動に失敗した場合。
    """
    container_name = get_container_name(session_id)
    host_workspace = str(workspace_base.resolve())
    image = get_image_name()

    result = subprocess.run(
        [
            "docker", "run", "-d",
            "--name", container_name,
            "-v", f"{host_workspace}:{CONTAINER_WORKSPACE}",
            "-e", f"{CONTAINER_FLAG_ENV}=1",
            "-e", f"WORKSPACE_BASE={CONTAINER_WORKSPACE}",
            "-e", f"SESSION_ID={session_id}",
            image,
            "sleep", "infinity",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"コンテナ '{container_name}' の起動に失敗しました: {result.stderr.strip()}"
        )
    return container_name


def stop_session_container(session_id: str) -> None:
    """セッション用の常駐 Docker コンテナを停止・削除する。

    コンテナが存在しない場合はエラーを無視する。

    :param session_id: セッション ID。
    """
    container_name = get_container_name(session_id)
    subprocess.run(
        ["docker", "stop", container_name],
        capture_output=True,
    )
    subprocess.run(
        ["docker", "rm", "--force", container_name],
        capture_output=True,
    )


def ensure_session_container(session_id: str, workspace_base: Path) -> str:
    """セッション用コンテナが実行中であることを保証する。

    コンテナが未起動の場合は :func:`start_session_container` を呼び出して起動する。
    既に実行中の場合はそのまま返す。

    :param session_id: セッション ID。
    :param workspace_base: ホスト側のワークスペースベースディレクトリ。
    :return: コンテナ名。
    """
    container_name = get_container_name(session_id)
    if not _is_container_running(container_name):
        start_session_container(session_id, workspace_base)
    return container_name


async def docker_exec_tool(
    session_id: str,
    name: str,
    arguments: str,
    cwd: str,
) -> str:
    """``docker exec`` を使ってコンテナ内でツールを実行する。

    コンテナ内の ``tool_runner.py`` に JSON を stdin で渡し、
    stdout の JSON から結果文字列を取り出す。

    ``APPLE_AGENT_SKIP_DOCKER=1`` が設定されている場合は
    ローカルの :func:`~apple_agent_core.tools.execute_tool` を直接呼ぶ。

    :param session_id: セッション ID（コンテナ名の特定に使用）。
    :param name: ツール名（"read", "write", "edit", "bash"）。
    :param arguments: JSON 文字列形式のツール引数。
    :param cwd: ツールが使用する作業ディレクトリ（コンテナ内パス）。
    :return: ツールの実行結果文字列。
    """
    if should_skip_docker():
        from .tools import execute_tool
        return execute_tool(name, arguments, cwd)

    container_name = get_container_name(session_id)
    request = json.dumps({"name": name, "arguments": arguments, "cwd": cwd}, ensure_ascii=False)

    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "exec", "-i", container_name,
            "python", "/app/src/apple_agent_core/tool_runner.py",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(request.encode()),
            timeout=EXEC_TIMEOUT,
        )
    except asyncio.TimeoutError:
        return f"[docker exec] タイムアウト: ツール '{name}' が {EXEC_TIMEOUT}s 以内に完了しませんでした。"
    except Exception as e:
        return f"[docker exec] エラー: {e}"

    if proc.returncode != 0:
        err = stderr.decode(errors="replace").strip()
        return f"[docker exec] ツール '{name}' がエラー終了しました (exit {proc.returncode}): {err}"

    try:
        result = json.loads(stdout.decode())
        return result.get("result", "")
    except json.JSONDecodeError:
        return stdout.decode(errors="replace")

