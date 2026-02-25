# 📚 Research Citation Assistant / 学术引用助手

![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)
![Flask](https://img.shields.io/badge/flask-2.3+-green.svg)
![License](https://img.shields.io/badge/license-MIT-purple.svg)

[English](#english) | [中文](#中文)

---

<br>

<h2 id="english">🇬🇧 English</h2>

**Research Citation Assistant** is an intelligent web application designed for researchers, academics, and students. It automatically analyzes your text, identifies sentences that require supporting evidence, and finds the most relevant academic papers to cite.

Stop wasting hours searching for that *one paper* you vaguely remember. Let the assistant find the perfect citations for your claims in seconds.

### ✨ Key Features

- 🔍 **Smart Citation Detection**: Automatically finds sentences in your text that make empirical claims or state facts needing citations.
- 🎓 **Semantic Paper Search**: Uses the Semantic Scholar API to find highly relevant, peer-reviewed academic papers.
- ⏱️ **Real-time Streaming**: Get results instantly as sentences are processed—no need to wait for the entire document to finish.
- 📑 **Multiple Formatting Styles**: Supports APA, MLA, Chicago, IEEE, Harvard, Vancouver, and BibTeX.
- 🎯 **Advanced Filtering**: Filter search results by publication year, specific journals/conferences, fields of study, minimum citation count, and open-access availability.
- 💾 **Export & Save**: Export your citations in Text, CSV, RIS, or BibTeX formats. Your session history is automatically saved locally.
- 🌓 **Dark Mode**: Built-in support for both light and dark themes to protect your eyes during late-night writing sessions.

### 🚀 Getting Started

#### Prerequisites
- Python 3.11+
- Semantic Scholar API Key (Optional but recommended for higher rate limits)

#### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/brandonsongli-ctrl/research-assistant.git
   cd research-assistant
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. (Optional) Configure environment variables:
   Copy `.env.example` to `.env` and add your Semantic Scholar API key.

4. Run the application:
   ```bash
   python app.py
   ```
   *Note: Ensure port 5000 is available, or modify the port in `app.py`.*

5. Open your browser and navigate to `http://localhost:5000` (or your configured port).

#### Docker Deployment

You can also run the application effortlessly using Docker:
```bash
docker-compose up -d --build
```

---

<br>

<h2 id="中文">🇨🇳 中文</h2>

**学术引用助手 (Research Citation Assistant)** 是一款专为研究人员、学者和学生设计的智能 Web 应用。它能够自动分析您的文本内容，精准定位需要学术证据支持的句子，并为您匹配和推荐最相关的学术论文文献。

不再为了寻找“似乎在哪里看过的那篇论文”而浪费数小时。让学术引用助手在几秒钟内为您的论点找到完美的学术支撑。

### ✨ 核心功能

- 🔍 **智能引用检测**：自动分析文本，找出陈述事实或提出经验性观点、急需文献支持的句子。
- 🎓 **语义文献检索**：基于 Semantic Scholar API，通过深度语义匹配为您寻找高质量的同行评审论文。
- ⏱️ **实时流式响应**：无需等待全文处理完毕，处理完一句即刻显示结果，体验如丝般顺滑。
- 📑 **多格式导出支持**：一键生成 APA, MLA, Chicago, IEEE, Harvard, Vancouver 以及 BibTeX 格式的引用。
- 🎯 **高级精准过滤**：支持按出版年份、特定期刊/会议、学科领域、最低被引频次以及是否开源（Open Access）进行精细化检索。
- 💾 **本地历史与导出**：一键将结果导出为 TXT、CSV、RIS 或 BibTeX 格式，您的检索历史也会自动在本地浏览器中保存。
- 🌓 **深色模式支持**：内置完善的深色/浅色主题切换，呵护那些深夜奋笔疾书的双眼。

### 🚀 快速开始

#### 环境要求
- Python 3.11 及以上版本
- Semantic Scholar API 密钥（可选，推荐配置以获得更高的调用额度）

#### 本地安装与运行

1. 克隆项目到本地：
   ```bash
   git clone https://github.com/brandonsongli-ctrl/research-assistant.git
   cd research-assistant
   ```

2. 创建虚拟环境并安装依赖：
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows 用户使用: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. (可选) 配置环境变量：
   将 `.env.example` 复制为 `.env`，并填入您的 Semantic Scholar API Key。

4. 启动应用：
   ```bash
   python app.py
   ```
   *注意：如果遇到 5000 端口被占用的情况，请修改 `app.py` 中的端口号，或使用 `flask run` 指定端口。*

5. 在浏览器中打开 `http://localhost:5000`（或您修改后的端口）即可使用。

#### Docker 一键部署

您也可以使用 Docker 轻松运行本项目：
```bash
docker-compose up -d --build
```

---

### 📄 License / 开源协议
This project is licensed under the MIT License - see the LICENSE file for details.
本项目基于 MIT 协议开源。
