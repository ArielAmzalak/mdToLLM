# -*- coding: utf-8 -*-
import os
import io
import re
import time
import base64
import shutil
import mimetypes
import tempfile
import requests
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

# --- GUI ---
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinterdnd2 import DND_FILES, TkinterDnD

# --- Conversão / LLM ---
from markitdown import MarkItDown
from openai import OpenAI

# --- Selenium (Firefox/Gecko) ---
from selenium import webdriver
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# ================== Configurações & Constantes ==================

base_dir = Path(__file__).resolve().parent

DOC_FORMATS = {".html", ".htm", ".docx", ".xlsx", ".pdf"}
IMG_FORMATS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif"}
TARGET_FORMATS = DOC_FORMATS | IMG_FORMATS

DEFAULT_MODEL = "gpt-4o-mini"  # custo/benefício para captioning
DEFAULT_PROMPT = (
    "Descreva a imagem em PT-BR para acessibilidade (ALT). "
    "Seja objetiva, cite texto visível e contexto; não invente."
)

# Tipos a baixar da página
RESOURCE_TAG_ATTRS = [
    ("img", "src"),
    ("script", "src"),
    ("link", "href"),         # CSS principalmente
    ("source", "src"),        # <picture>, <video>, <audio>
]

def load_openai_key_from_file():
    """
    Lê a OPENAI_API_KEY do arquivo OPENAI_API_KEY.txt (no mesmo diretório
    do script) e joga em os.environ["OPENAI_API_KEY"].
    
    Aceita:
        OPENAI_API_KEY = "minha_chave"
    ou só:
        minha_chave
    """
    key_path = Path(__file__).resolve().parent / "OPENAI_API_KEY.txt"
    if not key_path.exists():
        # Se não existir, não faz nada (continua dependendo do ambiente)
        return

    text = key_path.read_text(encoding="utf-8").strip()

    # Tenta formato: OPENAI_API_KEY = "chave"
    m = re.search(r'OPENAI_API_KEY\s*=\s*["\'](.+?)["\']', text)
    if m:
        key = m.group(1).strip()
    else:
        # Senão, assume que o arquivo contém só a chave (com ou sem aspas)
        key = text.strip().strip('"').strip("'")

    if key:
        os.environ["OPENAI_API_KEY"] = key


# ========================= Aplicação ============================

class MarkItDownApp(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title("Conversor p/ Markdown • MarkItDown + OpenAI + Selenium")
        self.geometry("720x680")

        # saída: mesma pasta do programa (como no original)               # (ref)
        self.output_dir = Path(__file__).resolve().parent

        # Estado OpenAI / MarkItDown
        self.use_openai = tk.BooleanVar(value=False)
        self.model_name = tk.StringVar(value=DEFAULT_MODEL)
        self.prompt_text = tk.StringVar(value=DEFAULT_PROMPT)
        self.desc_mode = tk.StringVar(value="markitdown")  # "markitdown" | "direct"

        # Estado Selenium
        self.url_text = tk.StringVar(value="")
        # self.gecko_path = tk.StringVar(value=str(base_dir / "firefox" / "geckodriver.exe"))
        # self.firefox_bin = tk.StringVar(value=str(base_dir / "firefox" / "firefox.exe"))
        self.gecko_path = tk.StringVar(value="C:\\Program Files\\Mozilla Firefox\\geckodriver.exe")
        self.firefox_bin = tk.StringVar(value="C:\\Program Files\\Mozilla Firefox\\firefox.exe")
        self.headless = tk.BooleanVar(value=True)

        self.md = self._build_markitdown()  # instancia o conversor
        self._criar_interface()

    # ----------------------------- UI ---------------------------------

    def _criar_interface(self):
        info = (
            "Arraste arquivos abaixo ou use 'Escolher arquivos'.\n"
            f"Extensões: {', '.join(sorted(TARGET_FORMATS))}\n"
            f"Saída (.md): {self.output_dir}"
        )
        tk.Label(self, text=info, justify="center").pack(pady=8)

        # Área de drop
        self.drop_area = tk.Label(self, text="⬇ Arraste arquivos aqui ⬇",
                                  relief="ridge", borderwidth=2, width=60, height=4)
        self.drop_area.pack(pady=6, padx=20, fill="x")
        self.drop_area.drop_target_register(DND_FILES)
        self.drop_area.dnd_bind("<<Drop>>", self._on_drop)

        # File picker
        row_btn = tk.Frame(self); row_btn.pack(pady=4)
        tk.Button(row_btn, text="Escolher arquivos…", command=self._selecionar_arquivos)\
            .pack(side="left", padx=5)

        # Painel OpenAI
        p_ai = tk.LabelFrame(self, text="Descrição de imagens (OpenAI)")
        p_ai.pack(padx=10, pady=8, fill="x")

        tk.Checkbutton(p_ai, text="Descrever imagens (OpenAI)",
                       variable=self.use_openai,
                       command=self._on_openai_toggle).pack(anchor="w", padx=8, pady=4)

        r1 = tk.Frame(p_ai); r1.pack(fill="x", padx=8, pady=2)
        tk.Label(r1, text="Modelo:").pack(side="left")
        tk.Entry(r1, textvariable=self.model_name, width=20).pack(side="left", padx=6)

        tk.Label(r1, text="Modo:").pack(side="left", padx=(10,0))
        mode = ttk.Combobox(r1, state="readonly", width=30,
                            values=["MarkItDown + OpenAI (recomendado)",
                                    "OpenAI direto (Responses API)"])
        mode.current(0)
        mode.bind("<<ComboboxSelected>>", lambda e: self._set_desc_mode(mode.current()))
        mode.pack(side="left", padx=6)

        r2 = tk.Frame(p_ai); r2.pack(fill="x", padx=8, pady=6)
        tk.Label(r2, text="Prompt:").pack(anchor="w")
        tk.Entry(r2, textvariable=self.prompt_text).pack(fill="x")

        # Painel Selenium / URL
        p_sel = tk.LabelFrame(self, text="Capturar página com Selenium (Firefox)")
        p_sel.pack(padx=10, pady=8, fill="x")

        r3 = tk.Frame(p_sel); r3.pack(fill="x", padx=8, pady=4)
        tk.Label(r3, text="URL:").pack(side="left")
        tk.Entry(r3, textvariable=self.url_text).pack(side="left", fill="x", expand=True, padx=6)
        tk.Button(r3, text="Capturar & Converter URL", command=self._capturar_converter_url)\
            .pack(side="left", padx=6)

        r4 = tk.Frame(p_sel); r4.pack(fill="x", padx=8, pady=4)
        tk.Label(r4, text="GeckoDriver:").pack(side="left")
        tk.Entry(r4, textvariable=self.gecko_path, width=40).pack(side="left", padx=6)
        tk.Label(r4, text="Firefox bin:").pack(side="left", padx=(10,0))
        tk.Entry(r4, textvariable=self.firefox_bin, width=30).pack(side="left", padx=6)

        tk.Checkbutton(p_sel, text="Headless (sem janela)", variable=self.headless)\
            .pack(anchor="w", padx=10, pady=4)

        # Log
        self.log = tk.Text(self, height=14, state="disabled")
        self.log.pack(padx=10, pady=10, fill="both", expand=True)

    def _set_desc_mode(self, idx: int):
        self.desc_mode.set("markitdown" if idx == 0 else "direct")
        self.md = self._build_markitdown()

    def _on_openai_toggle(self):
        self.md = self._build_markitdown()

    # ------------------------ Infra / Helpers --------------------------

    def _build_markitdown(self) -> MarkItDown:
        """
        Cria o MarkItDown. Se 'Descrever imagens' estiver ON e modo 'markitdown',
        passamos llm_client/model/prompt para que a descrição seja gerada quando
        a entrada for uma *imagem* isolada (PNG/JPG etc.).                     # (ref Real Python)
        """
        if self.use_openai.get() and self.desc_mode.get() == "markitdown":
            if not os.getenv("OPEN_API_KEY"):
                self._log("⚠ OPENAI_API_KEY não definido; descrição via MarkItDown desativada.")
                return MarkItDown()
            client = OpenAI()
            return MarkItDown(
                llm_client=client,
                llm_model=self.model_name.get().strip() or DEFAULT_MODEL,
                llm_prompt=self.prompt_text.get().strip() or DEFAULT_PROMPT,
            )
        return MarkItDown()

    def _log(self, msg: str):
        self.log.configure(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.insert("end", f"[{ts}] {msg}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    # ------------------------ Fluxos de Arquivo ------------------------

    def _on_drop(self, event):
        files = self.tk.splitlist(event.data)
        caminhos = [Path(f) for f in files if f]
        self._processar_arquivos(caminhos)

    def _selecionar_arquivos(self):
        tipos = [
            ("Todos suportados", " ".join(f"*{ext}" for ext in sorted(TARGET_FORMATS))),
            ("Imagens", "*.png *.jpg *.jpeg *.gif *.webp *.bmp *.tiff *.tif"),
            ("HTML", "*.html *.htm"),
            ("Word", "*.docx"),
            ("Excel", "*.xlsx"),
            ("PDF", "*.pdf"),
            ("Todos os arquivos", "*.*"),
        ]
        paths = filedialog.askopenfilenames(title="Escolher arquivos para converter",
                                            filetypes=tipos)
        if not paths: return
        self._processar_arquivos([Path(p) for p in paths])

    def _processar_arquivos(self, caminhos: list[Path]):
        if not caminhos: return
        ok = 0
        for caminho in caminhos:
            if not caminho.is_file():
                self._log(f"Ignorando (não é arquivo): {caminho}"); continue
            ext = caminho.suffix.lower()
            if ext not in TARGET_FORMATS:
                self._log(f"Ignorando (extensão não suportada): {caminho.name}"); continue
            try:
                if ext in IMG_FORMATS and self.use_openai.get() and self.desc_mode.get() == "direct":
                    markdown = self._descrever_imagem_via_openai(caminho)
                else:
                    markdown = self.md.convert(caminho).markdown
                out = self.output_dir / f"{caminho.stem}.md"
                out.write_text(markdown, encoding="utf-8")
                self._log(f"✓ Convertido {caminho.name} → {out.name}"); ok += 1
            except Exception as e:
                self._log(f"✗ Erro convertendo {caminho.name}: {e}")

        messagebox.showinfo("Concluído", f"Conversão finalizada. {ok} arquivo(s) gerado(s).")

    # --------------------------- Selenium ------------------------------

    def _capturar_converter_url(self):
        url = self.url_text.get().strip()
        if not url:
            messagebox.showwarning("URL vazia", "Informe uma URL."); return

        tmpdir = Path(tempfile.mkdtemp(prefix="mkd_snap_"))
        self._log(f"Capturando: {url}\nTemporários em: {tmpdir}")

        # Configura Selenium (Firefox)
        options = FirefoxOptions()
        if self.firefox_bin.get().strip():
            options.binary_location = self.firefox_bin.get().strip()
        if self.headless.get():
            options.add_argument("--headless")

        # Preferências de download (boa prática, ainda que baixemos via requests)
        options.set_preference("browser.download.folderList", 2)
        options.set_preference("browser.download.dir", str(tmpdir))
        options.set_preference("browser.download.manager.showWhenStarting", False)
        options.set_preference("browser.helperApps.neverAsk.saveToDisk",
                               "application/pdf,application/octet-stream,application/vnd.ms-excel")

        gecko = self.gecko_path.get().strip() or None
        service = FirefoxService(executable_path=gecko) if gecko else FirefoxService()

        driver = None
        try:
            driver = webdriver.Firefox(service=service, options=options)
            driver.set_page_load_timeout(60)
            driver.get(url)

            WebDriverWait(driver, 30).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            # tenta carregar lazy content
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            # user-agent para requests
            ua = driver.execute_script("return navigator.userAgent") or "Mozilla/5.0"

            # salva HTML
            html = driver.page_source
            html_path = tmpdir / "index.html"
            html_path.write_text(html, encoding="utf-8")
            self._log(f"• HTML salvo: {html_path.name}")

            # baixa recursos referenciados (img/css/js)
            assets_dir = tmpdir / "assets"; assets_dir.mkdir(exist_ok=True)
            images = self._baixar_recursos(driver.current_url, html, assets_dir, ua)
            self._log(f"• Recursos baixados: {len(images['all'])} (imagens: {len(images['imgs'])})")

            # converte HTML → Markdown (MarkItDown)
            md_text = self.md.convert(html_path).markdown

            # (opcional) gerar descrições para as imagens capturadas
            if self.use_openai.get() and images["imgs"]:
                # tenta carregar a chave do arquivo se ainda não estiver no ambiente
                if not os.getenv("OPENAI_API_KEY"):
                    load_openai_key_from_file()

                if not os.getenv("OPENAI_API_KEY"):
                    self._log("⚠ OPENAI_API_KEY não definido; pulando descrição de imagens.")
                else:
                    descricoes = []
                    for img_path in images["imgs"]:
                        try:
                            descr = self._gerar_alt_para_imagem(Path(img_path))
                            descricoes.append((img_path, descr))
                        except Exception as e:
                            self._log(f"Erro descrevendo {Path(img_path).name}: {e}")

                    if descricoes:
                        md_text += "\n\n## Descrições de imagens (captura Selenium)\n"
                        for pth, txt in descricoes:
                            md_text += f"- `{Path(pth).name}` — {txt}\n"


            # nome de saída baseado na URL
            out_name = self._slugify_url(driver.current_url) + ".md"
            out_path = self.output_dir / out_name
            out_path.write_text(md_text, encoding="utf-8")
            self._log(f"✓ URL convertida → {out_name}")

            messagebox.showinfo("Concluído", f"Gerei {out_name} na pasta do programa.")
        except (TimeoutException, WebDriverException) as e:
            self._log(f"✗ Selenium/Firefox: {e}")
            messagebox.showerror("Erro Selenium", str(e))
        except Exception as e:
            self._log(f"✗ Erro na captura/conversão: {e}")
            messagebox.showerror("Erro", str(e))
        finally:
            try:
                if driver: driver.quit()
            except Exception:
                pass
            # limpa temporários
            shutil.rmtree(tmpdir, ignore_errors=True)
            self._log("• Temporários removidos.")

    def _baixar_recursos(self, base_url: str, html: str, dest: Path, user_agent: str):
        """
        Percorre o DOM (via BeautifulSoup) e baixa recursos chave.
        Retorna dict com lista de 'all' e 'imgs' baixados.
        """
        from bs4 import BeautifulSoup

        session = requests.Session()
        session.headers.update({"User-Agent": user_agent})

        soup = BeautifulSoup(html, "html.parser")
        found_urls = set()
        img_paths = []

        def _save(url: str):
            try:
                r = session.get(url, timeout=30, stream=True)
                r.raise_for_status()
                # nome de arquivo baseado no path
                parsed = urlparse(url)
                fname = Path(parsed.path).name or "index"
                if not os.path.splitext(fname)[1]:
                    # tenta inferir pela resposta
                    ext = mimetypes.guess_extension(r.headers.get("Content-Type", ""), strict=False) or ""
                    fname = fname + ext
                # evita colisões
                target = dest / fname
                i = 1
                while target.exists():
                    stem, ext = os.path.splitext(fname)
                    target = dest / f"{stem}_{i}{ext}"
                    i += 1
                with open(target, "wb") as f:
                    shutil.copyfileobj(r.raw, f)
                return str(target)
            except Exception:
                return None

        # pega tags padrão
        for tag, attr in RESOURCE_TAG_ATTRS:
            for node in soup.find_all(tag):
                val = node.get(attr)
                if not val: continue
                abs_url = urljoin(base_url, val)
                if abs_url in found_urls: continue
                found_urls.add(abs_url)

        # tratamento básico de srcset (pega o primeiro candidato)
        for node in soup.find_all("img"):
            srcset = node.get("srcset")
            if srcset:
                candidate = srcset.split(",")[0].strip().split(" ")[0]
                abs_url = urljoin(base_url, candidate)
                if abs_url not in found_urls:
                    found_urls.add(abs_url)

        saved_all, saved_imgs = [], []
        for u in sorted(found_urls):
            local = _save(u)
            if local:
                saved_all.append(local)
                if Path(local).suffix.lower() in IMG_FORMATS:
                    saved_imgs.append(local)

        return {"all": saved_all, "imgs": saved_imgs}

    def _slugify_url(self, url: str) -> str:
        parsed = urlparse(url)
        text = f"{parsed.netloc}{parsed.path}"
        text = re.sub(r"[^a-zA-Z0-9_-]+", "_", text).strip("_")
        return text or "pagina"

    # ------------------ OpenAI direto (Responses API) ------------------

    def _gerar_alt_para_imagem(self, img_path: Path) -> str:
        """Gera **apenas** o texto ALT (string) via Responses API."""
        model = self.model_name.get().strip() or DEFAULT_MODEL
        prompt = self.prompt_text.get().strip() or DEFAULT_PROMPT
        client = OpenAI()

        mime, _ = mimetypes.guess_type(img_path.name)
        mime = mime or "image/png"
        b64 = base64.b64encode(img_path.read_bytes()).decode("utf-8")
        data_url = f"data:{mime};base64,{b64}"

        resp = client.responses.create(
            model=model,
            input=[{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": data_url},
                ],
            }],
        )
        return (resp.output_text or "").strip()

    def _descrever_imagem_via_openai(self, file_path: Path) -> str:
        """
        Constrói um Markdown simples com ALT + legenda para uma
        *imagem isolada*, usando a Responses API com data URL Base64.
        Docs oficiais: Quickstart / Images & Vision / SDK Python.       # (refs)
        """
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY não definido.")

        alt = self._gerar_alt_para_imagem(file_path)

        # garante que a imagem exista ao lado do .md (para o link)
        target_img = self.output_dir / file_path.name
        if not target_img.exists():
            shutil.copy2(file_path, target_img)

        md = []
        md.append(f"![{alt}]({target_img.name})\n")
        md.append("**Descrição:** " + alt + "\n")
        md.append(f"\n<sub>Gerado por {self.model_name.get()} em "
                  f"{datetime.now().isoformat(timespec='seconds')}</sub>\n")
        return "".join(md)


def main():
    # carrega a chave da OpenAI do arquivo, antes de criar a UI
    load_openai_key_from_file()

    app = MarkItDownApp()
    app.mainloop()

if __name__ == "__main__":
    main()
