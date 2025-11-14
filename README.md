Acesse o link para o Firefox portátil e o geckodriver.exe dento da pasta
https://drive.google.com/drive/folders/1gHBJ7Mi70ySKU5U0I8hpW7n3XR7maPNu?usp=sharing

# Conversor para Markdown — MarkItDown + OpenAI + Selenium

Aplicativo desktop (Tkinter) para converter arquivos e páginas da web em **Markdown (`.md`)**, com suporte a:

* Arrastar e soltar arquivos (drag & drop)
* Conversão de documentos (HTML, DOCX, XLSX, PDF etc.) usando **[MarkItDown](https://github.com/microsoft/markitdown)**
* Geração de descrições de **imagens via OpenAI** (ALT em PT-BR para acessibilidade)
* Captura de **páginas web com Selenium + Firefox**, download de assets (imagens/CSS/JS) e conversão para Markdown

A saída é sempre um arquivo `.md` gerado na mesma pasta do programa.

---

## Funcionalidades

### 1. Conversão de arquivos para Markdown

Suporta as extensões:

* Documentos: `.html`, `.htm`, `.docx`, `.xlsx`, `.pdf`
* Imagens: `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.bmp`, `.tiff`, `.tif`, `.svg`

Fluxo:

* Arraste arquivos para a área de drop ou clique em **“Escolher arquivos…”**
* O app converte cada arquivo suportado em um `NOME_DO_ARQUIVO.md`
* Os `.md` são salvos na mesma pasta onde está o programa/script

### 2. Descrição de imagens (OpenAI)

Opcionalmente, o app pode descrever imagens em PT-BR usando a API da OpenAI:

* Gera texto **ALT** objetivo, sem inventar informações
* Cita texto visível e contexto da imagem
* Pode funcionar de duas formas:

  * **MarkItDown + OpenAI (recomendado)**: o MarkItDown converte e chama o modelo da OpenAI internamente quando a entrada é uma imagem isolada.
  * **OpenAI direto (Responses API)**: o app monta um Markdown simples com:

    * `![ALT](arquivo.png)`
    * **Descrição:** texto retornado pelo modelo
    * Rodapé com modelo usado e timestamp

### 3. Captura de páginas web com Selenium + Firefox

* Informa uma URL e clica em **“Capturar & Converter URL”**
* O app:

  1. Abre a página no Firefox (Selenium), opcionalmente em modo headless
  2. Faz auto-scroll para forçar o carregamento de conteúdo lazy
  3. Salva o HTML bruto
  4. Baixa recursos relacionados (imagens, CSS, JS) com `requests`
  5. Reescreve o HTML para apontar para os assets baixados localmente
  6. Converte o HTML reescrito para Markdown usando MarkItDown
  7. (Opcional) Gera uma seção **“Descrições de imagens (captura Selenium)”** com ALT das imagens via OpenAI

Os assets são copiados para uma pasta ao lado do `.md`, no formato:

* `slug_da_url.md`
* `slug_da_url_assets/` (imagens, CSS, JS, etc.)

---

## Requisitos

### Python

* Python 3.10+ (recomendado)

### Bibliotecas Python

Instale, por exemplo:

```bash
pip install markitdown openai selenium requests beautifulsoup4 tkinterdnd2
```

> Obs.: `tkinter` vem junto com o Python padrão em muitas instalações (principalmente no Windows).
> Se estiver em Linux/macOS pode ser necessário instalar o pacote gráfico adequado da distribuição.

### Navegador & WebDriver (Selenium)

Para o recurso de **capturar URL**:

* **Firefox** instalado
* **GeckoDriver** compatível com a versão do Firefox

Por padrão, o código espera (no mesmo diretório do script):

* `firefox/firefox.exe`
* `firefox/geckodriver.exe`

Mas esses caminhos podem ser alterados na interface:

* Campos **“GeckoDriver”** e **“Firefox bin”** no painel *“Capturar página com Selenium (Firefox)”*

Em Linux/macOS, você pode:

* Deixar o Firefox no `PATH`
* Deixar o `geckodriver` no `PATH`
* Ajustar os campos na UI conforme seu ambiente

---

## Configuração da OpenAI (OPENAI_API_KEY)

A chave da OpenAI é carregada automaticamente do arquivo:

* `OPENAI_API_KEY.txt` (no mesmo diretório do script)

O arquivo pode estar em um dos formatos:

```txt
OPENAI_API_KEY = "sua_chave_aqui"
```

ou simplesmente:

```txt
sua_chave_aqui
```

O código:

* Lê o arquivo
* Extrai a chave
* Seta `os.environ["OPENAI_API_KEY"]`

Se nenhuma chave for encontrada:

* Ainda é possível converter documentos com MarkItDown normalmente
* Recursos que dependem da OpenAI (descrição de imagens) não funcionarão e serão ignorados com avisos no log

---

## Como executar

1. Clone/baixe este repositório
2. Instale as dependências Python:

   ```bash
   pip install markitdown openai selenium requests beautifulsoup4 tkinterdnd2
   ```
3. Crie o arquivo `OPENAI_API_KEY.txt` (se for usar OpenAI)
4. Ajuste (se necessário) os caminhos de Firefox/GeckoDriver (ou deixe o padrão se estiver usando a pasta `firefox/` local)
5. Execute o script:

   ```bash
   python nome_do_arquivo.py
   ```

   (Substitua pelo nome real do arquivo, por exemplo `app.py`.)

A janela principal será aberta com:

* Área de drag & drop
* Botão **“Escolher arquivos…”**
* Painel de configuração OpenAI
* Painel de captura de URL via Selenium
* Área de log (parte inferior)

---

## Uso — passo a passo

### 1. Converter arquivos locais

1. Abra o programa
2. Arraste arquivos suportados para a área **“⬇ Arraste arquivos aqui ⬇”**, ou clique em **“Escolher arquivos…”**
3. O log exibirá:

   * Arquivos ignorados (extensão não suportada ou não é arquivo)
   * Arquivos convertidos
4. Ao final, aparece um `messagebox` informando quantos arquivos `.md` foram gerados

Saída:

* Para cada arquivo `arquivo.ext` suportado, será gerado `arquivo.md` na pasta do programa.

### 2. Ativar/usar descrição de imagens (OpenAI)

No painel **“Descrição de imagens (OpenAI)”**:

* Marque **“Descrever imagens (OpenAI)”**
* Campo **Modelo**:

  * Padrão: `gpt-4o-mini` (custo/benefício)
  * Pode ser trocado por outro modelo compatível
* Campo **Prompt**:

  * Padrão: prompt em PT-BR focado em acessibilidade (ALT)
  * Pode ser customizado

Selecione o **Modo** (Combobox):

1. **“MarkItDown + OpenAI (recomendado)”**

   * O MarkItDown chama o LLM quando a entrada é uma imagem isolada.
   * Ideal para fluxos mistos e uso mais automático.

2. **“OpenAI direto (Responses API)”**

   * Para arquivos de imagem processados diretamente pelo app (sem MarkItDown cuidar da descrição).
   * O app:

     * Envia a imagem como data URL Base64 para o modelo
     * Gera um Markdown simples com:

       * `![ALT](nome_da_imagem)`
       * `**Descrição:** ALT`
       * Rodapé com modelo e timestamp

> Importante: se `OPENAI_API_KEY` não estiver definida, o app avisa no log e não tenta chamar a API.

### 3. Capturar e converter uma página web (Selenium)

No painel **“Capturar página com Selenium (Firefox)”**:

1. Campo **URL:**

   * Digite a URL que deseja capturar
2. Ajuste (se necessário):

   * **GeckoDriver**: caminho para o executável do geckodriver
   * **Firefox bin**: caminho para o executável do Firefox
   * Checkbox **“Headless (sem janela)”**:

     * Ligado: execução sem abrir janela gráfica
3. Clique em **“Capturar & Converter URL”**

O que acontece:

* O app abre a página no Firefox controlado pelo Selenium
* Espera o `document.readyState == "complete"`
* Faz auto-scroll até estabilizar a altura da página
* Salva o HTML como `index.html` em uma pasta temporária
* Usa `requests` + cookies do Selenium para baixar:

  * Imagens (`img`, `source`, `srcset`)
  * CSS (`link href`)
  * JS (`script src`)
  * Apenas tipos permitidos (`image/*`, `text/css`, `application/javascript` etc.)
  * Limite de tamanho por arquivo (8 MB)
* Reescreve o HTML para apontar para os arquivos baixados em uma pasta `_assets`
* Converte o HTML final para Markdown (`slug_da_url.md`)
* Opcionalmente, gera uma seção adicional com descrições das imagens capturadas

Limitações:

* Tamanho máximo de asset (`MAX_ASSET_BYTES`) = 8 MB
* Alguns tipos de recursos complexos podem não ser baixados/conectados
* Páginas que exigem autenticação podem precisar do Selenium já autenticado (cookies são reaproveitados na sessão `requests`, mas o login em si não é automatizado aqui)

---

## Log e mensagens

A área de log (parte inferior da janela):

* Exibe timestamp `[HH:MM:SS]` e mensagens de status
* Exemplos:

  * `✓ Convertido arquivo.pdf → arquivo.md`
  * `✗ Erro convertendo imagem.png: ...`
  * `⚠ OPENAI_API_KEY não definido; descrição via MarkItDown desativada.`
  * `• HTML salvo: index.html`
  * `• Recursos baixados: X (imagens: Y)`
  * `• Temporários removidos.`

Também são usadas janelas de mensagem (`messagebox`) para:

* Avisar conclusão de conversão
* Avisar URL vazia
* Exibir erros de Selenium/OpenAI/etc.

---

## Estrutura geral do código

* `load_openai_key_from_file()`
  Lê `OPENAI_API_KEY.txt` e configura a variável de ambiente.

* `MarkItDownApp(TkinterDnD.Tk)`
  Classe principal da aplicação (Tkinter + TkinterDnD):

  * Configuração de estado (variáveis Tkinter)
  * Construção da interface (`_criar_interface`)
  * Criação/atualização da instância do MarkItDown (`_build_markitdown`)
  * Conversão de arquivos (`_processar_arquivos`)
  * Captura de URL & conversão (`_capturar_converter_url`)
  * Download de assets (`_baixar_recursos`)
  * Reescrita de HTML para usar assets locais (`_rewrite_html_with_local_assets`)
  * Transferência de cookies do Selenium para `requests` (`_attach_cookies_from_driver`)
  * Auto-scroll de página (`_auto_scroll`)
  * Geração de slugs para nomes de arquivos a partir de URLs (`_slugify_url`)
  * Chamadas diretas à OpenAI para descrição de imagens (`_gerar_alt_para_imagem`, `_descrever_imagem_via_openai`)

* `main()`

  * Carrega a chave da OpenAI
  * Inicializa `MarkItDownApp` e entra no loop Tkinter
