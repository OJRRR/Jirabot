FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 创建运行时目录
RUN mkdir -p reports logs data uploads sessions

# 默认启动 Web 服务
CMD ["python", "webapp.py"]

EXPOSE 5000
