qBittorrent 基于python，自动分类脚本。可在添加种子时，自动将种子分类为电影，电视剧，其他。并转移至分类文件夹。

创建Dockerfile和scripts内两个文件，congfig需自行修改。

docker compose up -d --build重新构建镜像

qbit内新增 Torrent 时运行：/opt/venv/bin/python3 /scripts/qbit_classifier.py "%I" "%N" "%F"
