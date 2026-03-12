"""Docker コンテナ管理モジュール。

セッションごとに Docker コンテナを起動し、エージェントを隔離実行する。
ホスト側のランチャーと、コンテナ側のエージェントの両方からインポートされる。
"""

import asyncio
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
    # プロジェクトルート: src/apple_agent_core/docker.py から 3 階層上
    project_root = Path(__file__).parent.parent.parent
    dockerfile = project_root / "docker" / "Dockerfile"

    build_result = subprocess.run(
        ["docker", "build", "-t", name, "-f", str(dockerfile), str(project_root)],
    )
    if build_result.returncode != 0:
        print(f"[docker] ビルドに失敗しました。手動でビルドしてください: docker build -t {name} -f docker/Dockerfile .", file=sys.stderr)
        return False

    print(f"[docker] イメージ '{name}' をビルドしました。")
    return True


def _build_docker_run_args(
    session_id: str,
    workspace_base: Path,
    *,
    interactive: bool = False,
) -> list[str]:
    """``docker run`` の共通引数リストを生成する。

    :param session_id: セッション ID。コンテナに環境変数として渡される。
    :param workspace_base: ホスト側のワークスペースベースディレクトリ（絶対パス）。
    :param interactive: ``True`` の場合は ``-it`` フラグを追加する（CLI 用）。
    :return: ``docker run`` に渡す引数リスト（"docker" を含まない）。
    """
    host_workspace = str(workspace_base.resolve())
    image = get_image_name()

    flags = ["run", "--rm"]
    if interactive:
        flags.append("-it")
    else:
        flags.append("-i")

    args = flags + [
        "-v", f"{host_workspace}:{CONTAINER_WORKSPACE}",
        "-e", f"{CONTAINER_FLAG_ENV}=1",
        "-e", f"WORKSPACE_BASE={CONTAINER_WORKSPACE}",
        "-e", f"SESSION_ID={session_id}",
    ]

    # ホスト環境変数を選択的に引き継ぐ
    for key in ("OPENROUTER_API_KEY", "MODEL", "LOG_LEVEL"):
        val = os.environ.get(key)
        if val:
            args += ["-e", f"{key}={val}"]

    args.append(image)
    return args


def exec_cli_container(session_id: str, workspace_base: Path) -> None:
    """CLI セッション用 Docker コンテナを起動し、現在のプロセスを置換する。

    ``os.execvp`` を使うため、この関数は正常終了しない。
    ユーザーはコンテナの stdin/stdout/stderr に直接接続される。

    :param session_id: セッション ID。
    :param workspace_base: ホスト側のワークスペースベースディレクトリ。
    """
    docker_args = _build_docker_run_args(session_id, workspace_base, interactive=True)
    # entrypoint.sh が引数なしで agent を起動する
    cmd = ["docker"] + docker_args
    os.execvp("docker", cmd)


async def create_stdio_subprocess(
    session_id: str,
    workspace_base: Path,
) -> asyncio.subprocess.Process:
    """Web UI 用 Docker コンテナを stdio モードで非同期に起動する。

    コンテナは ``--stdio`` フラグを受け取り、JSON-line プロトコルで
    stdin/stdout を通じてホストと通信する。

    :param session_id: セッション ID。
    :param workspace_base: ホスト側のワークスペースベースディレクトリ。
    :return: 起動した Docker コンテナのサブプロセス。
    """
    docker_args = _build_docker_run_args(session_id, workspace_base, interactive=False)
    cmd = ["docker"] + docker_args + ["--stdio"]

    return await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
