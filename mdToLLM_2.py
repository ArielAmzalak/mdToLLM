# -*- coding: utf-8 -*-
import os
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
from selenium.common.exceptions import TimeoutException, WebDriverException

# ================== Configurações & Constantes ==================

base_dir = Path(__file__).resolve().parent

DOC_FORMATS = {".html", ".htm", ".docx", ".xlsx", ".pdf"}
IMG_FORMATS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif", ".svg"}
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

# Limites para download de assets
MAX_ASSET_BYTES = 8 * 1024 * 1024  # 8 MB
ALLOWED_MIME_PREFIXES = (
    "image/", "text/css", "application/javascript", "text/javascript", "application/x-javascript"
)

# ================== OPENAI KEY LOADER ===========================

def load_openai_key_from_file():
    """
    Lê a OPENAI_API_KEY do arquivo OPENAI_API_KEY.txt (no mesmo diretório
    do script) e joga em os.environ["OPENAI_API_KEY"].

    Aceita:
        OPENAI_API_KEY = "minha_chave"
    ou só:
        minha_chave
    """
    key_path = base_dir / "OPENAI_API_KEY.txt"
    if not key_path.exists():
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
        self.geometry("760x720")

        # saída: mesma pasta do programa
        self.output_dir = base_dir

        # Estado OpenAI / MarkItDown
        self.use_openai = tk.BooleanVar(value=False)
        self.model_name = tk.StringVar(value=DEFAULT_MODEL)
        self.prompt_text = tk.StringVar(value=DEFAULT_PROMPT)
        self.desc_mode = tk.StringVar(value="markitdown")  # "markitdown" | "direct"

        # Estado Selenium (Firefox portátil por padrão)
        self.url_text = tk.StringVar(value="")
        self.gecko_path = tk.StringVar(value=str(base_dir / "firefox" / "geckodriver.exe"))
        self.firefox_bin = tk.StringVar(value=str(base_dir / "firefox" / "firefox.exe"))
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
                                  relief="ridge", borderwidth=2, width=70, height=4)
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
        tk.Entry(r4, textvariable=self.gecko_path, width=45).pack(side="left", padx=6)
        tk.Label(r4, text="Firefox bin:").pack(side="left", padx=(10,0))
        tk.Entry(r4, textvariable=self.firefox_bin, width=34).pack(side="left", padx=6)

        tk.Checkbutton(p_sel, text="Headless (sem janela)", variable=self.headless)\
            .pack(anchor="w", padx=10, pady=4)

        # Log
        self.log = tk.Text(self, height=16, state="disabled")
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
        a entrada for uma *imagem* isolada (PNG/JPG etc.).
        """
        if self.use_openai.get() and self.desc_mode.get() == "markitdown":
            if not os.getenv("OPENAI_API_KEY"):
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
            ("Imagens", "*.png *.jpg *.jpeg *.gif *.webp *.bmp *.tiff *.tif *.svg"),
            ("HTML", "*.html *.htm"),
            ("Word", "*.docx"),
            ("Excel", "*.xlsx"),
            ("PDF", "*.pdf"),
            ("Todos os arquivos", "*.*"),
        ]
        paths = filedialog.askopenfilenames(title="Escolher arquivos para converter",
                                            filetypes=tipos)
        if not paths: 
            return
        self._processar_arquivos([Path(p) for p in paths])

    def _processar_arquivos(self, caminhos: list[Path]):
        if not caminhos: 
            return
        ok = 0
        for caminho in caminhos:
            if not caminho.is_file():
                self._log(f"Ignorando (não é arquivo): {caminho}")
                continue
            ext = caminho.suffix.lower()
            if ext not in TARGET_FORMATS:
                self._log(f"Ignorando (extensão não suportada): {caminho.name}")
                continue
            try:
                if ext in IMG_FORMATS and self.use_openai.get() and self.desc_mode.get() == "direct":
                    markdown = self._descrever_imagem_via_openai(caminho)
                else:
                    markdown = self.md.convert(caminho).markdown
                out = self.output_dir / f"{caminho.stem}.md"
                out.write_text(markdown, encoding="utf-8")
                self._log(f"✓ Convertido {caminho.name} → {out.name}")
                ok += 1
            except Exception as e:
                self._log(f"✗ Erro convertendo {caminho.name}: {e}")

        messagebox.showinfo("Concluído", f"Conversão finalizada. {ok} arquivo(s) gerado(s).")

    # --------------------------- Selenium ------------------------------

    def _capturar_converter_url(self):
        url = self.url_text.get().strip()
        if not url:
            messagebox.showwarning("URL vazia", "Informe uma URL.")
            return

        tmpdir = Path(tempfile.mkdtemp(prefix="mkd_snap_"))
        self._log(f"Capturando: {url}\nTemporários em: {tmpdir}")

        # Configura Selenium (Firefox)
        options = FirefoxOptions()
        if self.firefox_bin.get().strip():
            options.binary_location = self.firefox_bin.get().strip()
        if self.headless.get():
            options.add_argument("--headless")

        # Preferências de download (usamos requests, mas isso não atrapalha)
        options.set_preference("browser.download.folderList", 2)
        options.set_preference("browser.download.dir", str(tmpdir))
        options.set_preference("browser.download.manager.showWhenStarting", False)
        options.set_preference(
            "browser.helperApps.neverAsk.saveToDisk",
            "application/pdf,application/octet-stream,application/vnd.ms-excel"
        )

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
            # auto-scroll para carregar lazy content
            self._auto_scroll(driver, pause=0.8, max_steps=20)

            # user-agent para requests
            ua = driver.execute_script("return navigator.userAgent") or "Mozilla/5.0"

            # salva HTML bruto
            html = driver.page_source
            html_path = tmpdir / "index.html"
            html_path.write_text(html, encoding="utf-8")
            self._log(f"• HTML salvo: {html_path.name}")

            # baixa recursos referenciados (img/css/js)
            assets_dir = tmpdir / "assets"
            assets_dir.mkdir(exist_ok=True)
            images = self._baixar_recursos(driver.current_url, html, assets_dir, ua, driver=driver)
            self._log(f"• Recursos baixados: {len(images['all'])} (imagens: {len(images['imgs'])})")

            # move assets para pasta definitiva ao lado do .md
            slug = self._slugify_url(driver.current_url)
            final_assets_dir = self.output_dir / f"{slug}_assets"
            final_assets_dir.mkdir(exist_ok=True)

            # Atualiza mapa e lista de imagens para apontar para o destino final
            updated_img_list = []
            for src_path in images["all"]:
                src = Path(src_path)
                tgt = final_assets_dir / src.name
                i = 1
                while tgt.exists():
                    stem, ext = os.path.splitext(src.name)
                    tgt = final_assets_dir / f"{stem}_{i}{ext}"
                    i += 1
                shutil.copy2(src, tgt)

                # Atualiza map URL → caminho final
                for k, v in list(images["map"].items()):
                    if v == str(src):
                        images["map"][k] = str(tgt)

                # Atualiza lista de imagens
                if src.suffix.lower() in IMG_FORMATS:
                    updated_img_list.append(str(tgt))

            images["imgs"] = updated_img_list

            # reescreve HTML (no tmp) para apontar pros assets locais (relativos ao output_dir)
            html_rewritten = self._rewrite_html_with_local_assets(
                html=html,
                base_url=driver.current_url,
                url_map=images["map"],
                final_assets_dir=final_assets_dir
            )
            html_path.write_text(html_rewritten, encoding="utf-8")

            # converte HTML → Markdown (MarkItDown)
            md_text = self.md.convert(html_path).markdown

            # (opcional) gerar descrições para as imagens capturadas
            if self.use_openai.get() and images["imgs"]:
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
            out_name = slug + ".md"
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
                if driver:
                    driver.quit()
            except Exception:
                pass
            # limpa temporários
            shutil.rmtree(tmpdir, ignore_errors=True)
            self._log("• Temporários removidos.")

    # --------------------------- Helpers Selenium/Assets ----------------

    def _baixar_recursos(self, base_url: str, html: str, dest: Path, user_agent: str, driver=None):
        """
        Percorre o DOM (via BeautifulSoup) e baixa recursos-chave.
        Transfere cookies do Selenium (se houver).
        Aplica limites de MIME/tamanho.
        Retorna dict com: 'all' (todos salvos), 'imgs' (apenas imagens) e 'map' (URL -> caminho local).
        """
        from bs4 import BeautifulSoup

        session = requests.Session()
        session.headers.update({"User-Agent": user_agent})
        if driver:
            self._attach_cookies_from_driver(driver, session)

        soup = BeautifulSoup(html, "html.parser")
        found_urls = set()
        url_to_local = {}

        def _save(url: str):
            try:
                r = session.get(url, timeout=30, stream=True)
                r.raise_for_status()

                ctype = r.headers.get("Content-Type", "")
                if not any(ctype.startswith(p) for p in ALLOWED_MIME_PREFIXES):
                    return None

                size = r.headers.get("Content-Length")
                if size and int(size) > MAX_ASSET_BYTES:
                    return None

                parsed = urlparse(url)
                fname = Path(parsed.path).name or "index"
                if not os.path.splitext(fname)[1]:
                    # tenta inferir pela resposta
                    ext = mimetypes.guess_extension(ctype, strict=False) or ""
                    fname = fname + ext

                target = dest / fname
                i = 1
                while target.exists():
                    stem, ext = os.path.splitext(fname)
                    target = dest / f"{stem}_{i}{ext}"
                    i += 1

                total = 0
                with open(target, "wb") as f:
                    for chunk in r.iter_content(8192):
                        if not chunk:
                            continue
                        total += len(chunk)
                        if total > MAX_ASSET_BYTES:
                            f.close()
                            try:
                                os.remove(target)
                            except Exception:
                                pass
                            return None
                        f.write(chunk)

                url_to_local[url] = str(target)
                return str(target)
            except Exception:
                return None

        # coleta URLs dos atributos alvo
        for tag, attr in RESOURCE_TAG_ATTRS:
            for node in soup.find_all(tag):
                val = node.get(attr)
                if not val:
                    continue
                abs_url = urljoin(base_url, val)
                found_urls.add(abs_url)

        # tratamento básico de srcset (pega o primeiro candidato)
        for node in soup.find_all("img"):
            srcset = node.get("srcset")
            if srcset:
                candidate = srcset.split(",")[0].strip().split(" ")[0]
                abs_url = urljoin(base_url, candidate)
                found_urls.add(abs_url)

        saved_all, saved_imgs = [], []
        for u in sorted(found_urls):
            local = _save(u)
            if local:
                saved_all.append(local)
                if Path(local).suffix.lower() in IMG_FORMATS:
                    saved_imgs.append(local)

        return {"all": saved_all, "imgs": saved_imgs, "map": url_to_local}

    def _rewrite_html_with_local_assets(self, html: str, base_url: str, url_map: dict, final_assets_dir: Path) -> str:
        """
        Reescreve o HTML para referenciar os assets locais (em final_assets_dir),
        usando caminhos relativos ao diretório de saída (self.output_dir).
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")

        def rel_for(url: str):
            local = url_map.get(url)
            if not local:
                return None
            # caminho relativo a partir do local do .md (output_dir)
            return os.path.relpath(local, start=self.output_dir)

        targets = [
            ("img", "src"),
            ("source", "src"),
            ("script", "src"),
            ("link", "href"),
        ]

        for tag, attr in targets:
            for node in soup.find_all(tag):
                val = node.get(attr)
                if not val:
                    continue
                abs_url = urljoin(base_url, val)
                new_rel = rel_for(abs_url)
                if new_rel:
                    node[attr] = new_rel.replace("\\", "/")  # normaliza separador p/ Markdown

        return str(soup)

    def _attach_cookies_from_driver(self, driver, session: requests.Session):
        """Copia cookies do Selenium para a sessão requests (útil p/ páginas autenticadas)."""
        try:
            cookies = driver.get_cookies()
        except Exception:
            cookies = []
        for c in cookies:
            try:
                session.cookies.set(
                    c.get("name"), c.get("value"),
                    domain=c.get("domain"), path=c.get("path", "/")
                )
            except Exception:
                pass

    def _auto_scroll(self, driver, pause=0.8, max_steps=20):
        """Rola a página até estabilizar a altura (ou atingir max_steps)."""
        last_h = 0
        for _ in range(max_steps):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(pause)
            h = driver.execute_script("return document.body.scrollHeight") or 0
            if h == last_h:
                break
            last_h = h

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

        try:
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
        except Exception as e:
            self._log(f"OpenAI erro: {e}")
            return ""

    def _descrever_imagem_via_openai(self, file_path: Path) -> str:
        """
        Constrói um Markdown simples com ALT + legenda para uma
        *imagem isolada*, usando a Responses API com data URL Base64.
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
        md.append("**Descrição:** " + (alt or "(sem descrição)") + "\n")
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
