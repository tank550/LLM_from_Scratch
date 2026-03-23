import requests
from bs4 import BeautifulSoup
import json
import csv
import time
import re

class Africouleur:

    def __init__(self, url):
        self.url = url
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        self.all_products = []

    # -------------------------------------------------------------------------
    # Modèle d'un produit
    # -------------------------------------------------------------------------
    def product_info(self):
        return {
            "name": None,
            "price_eur": None,
            "price_fcfa": None,
            "description": None,
            "short_description": None,
            "list_image_product_url": None,
            "category": None,
            "sub_category": None,
            "sub_sub_category": None,
            "tags": None,
            "url_product": None,
        }

    # -------------------------------------------------------------------------
    # Récupère et parse une page (avec retry simple)
    # -------------------------------------------------------------------------
    def get_page(self, url, retries=3):
        for attempt in range(retries):
            try:
                response = self.session.get(url, timeout=15)
                response.raise_for_status()
                return BeautifulSoup(response.text, "html.parser")
            except requests.exceptions.RequestException as e:
                print(f"  [ERREUR] Tentative {attempt+1}/{retries} échouée pour {url} : {e}")
                time.sleep(2)
        print(f"  [ABANDON] Impossible de charger : {url}")
        return None

    # -------------------------------------------------------------------------
    # Point d'entrée : scrape la page d'accueil pour trouver les catégories
    # -------------------------------------------------------------------------
    def scrape_website(self):
        print(f"\n{'='*60}")
        print(f"Démarrage du scraping : {self.url}")
        print(f"{'='*60}")

        soup = self.get_page(self.url)
        if not soup:
            return

        # URLs de remplacement pour les catégories qui redirigent automatiquement.
        # Si le site redirige /enfant/ vers /enfant/vetement-enfant/, on force
        # l'URL /boutique/enfant/ qui affiche correctement toutes les sous-catégories.
        URL_OVERRIDES = {
            "Enfant": "https://www.africouleur.com/boutique/enfant/",
        }

        global_categories = soup.select('div[id^="row-"]')
        print(f"Catégories principales trouvées : {len(global_categories)}")

        for global_category in global_categories:
            for link in global_category.select('h2 a'):
                category_name = link.get_text(strip=True)
                category_url  = URL_OVERRIDES.get(category_name, link['href'])
                if category_url != link['href']:
                    print(f"\n>> Catégorie : {category_name} [URL remplacée → {category_url}]")
                else:
                    print(f"\n>> Catégorie : {category_name}")
                self.scrape_category_page(category_url, category_name)

    # -------------------------------------------------------------------------
    # Explore une page qui peut contenir des sous-catégories OU des produits
    # -------------------------------------------------------------------------
    def scrape_category_page(self, url, category_name, depth=0):
        if depth > 4:
            return

        soup = self.get_page(url)
        if not soup:
            return

        # Cas 1 : la page liste des sous-catégories
        sub_cats = soup.find_all(class_="product-category")
        if sub_cats:
            print(f"  {'  '*depth}Sous-catégories ({len(sub_cats)}) dans '{category_name}'")
            for sub in sub_cats:
                link = sub.select_one('a')
                name_el = sub.select_one('h2, h3, h5')
                if link and name_el:
                    sub_url  = link['href']
                    sub_name = name_el.get_text(strip=True)
                    print(f"  {'  '*depth}  -> {sub_name}")
                    self.scrape_category_page(sub_url, sub_name, depth + 1)
            return

        # Cas 2 : la page liste directement des produits
        self.scrape_products_page(url, category_name)

    # -------------------------------------------------------------------------
    # Scrape toutes les pages de produits d'une catégorie (pagination incluse)
    # -------------------------------------------------------------------------
    def scrape_products_page(self, base_url, category_name):
        page_num = 1
        while True:
            url = base_url if page_num == 1 else f"{base_url.rstrip('/')}/page/{page_num}/"
            print(f"    [Page {page_num}] {url}")

            soup = self.get_page(url)
            if not soup:
                break

            products = soup.find_all('div', class_='type-product')
            if not products:
                print(f"    Fin de pagination à la page {page_num}.")
                break

            print(f"    {len(products)} produits trouvés")

            for product in products:
                product_link = product.select_one('a')
                if product_link and product_link.get('href'):
                    self.scrape_single_product(product_link['href'], category_name)
                    time.sleep(0.3)

            next_page = soup.select_one('a.next.page-numbers')
            if not next_page:
                break
            page_num += 1

    # -------------------------------------------------------------------------
    # Scrape les détails d'un seul produit
    # -------------------------------------------------------------------------

    # Texte publicitaire à exclure de toutes les descriptions
    TEXTE_A_EXCLURE = (
        "Venez visiter notre boutique au 108 rue st Maur Paris 11ème "
        "pour découvrir, toucher et vous imprégner d'un large choix de nos créations."
    )

    def scrape_single_product(self, url, category_name):
        soup = self.get_page(url)
        if not soup:
            return

        # --- Nom ---
        name_el = soup.select_one('.product-title, h1.product_title')
        name = name_el.get_text(strip=True) if name_el else "N/A"

        # --- Prix ---
        price_el = soup.select_one('.product-page-price bdi, .price bdi')
        price_eur  = None
        price_fcfa = None
        if price_el:
            raw = price_el.get_text(strip=True).replace('\xa0', '').replace('€', '').replace(',', '.').strip()
            try:
                price_eur  = float(raw)
                price_fcfa = round(price_eur * 655.957)
            except ValueError:
                pass

        # --- Images ---
        images = [
            img['src'] for img in soup.select('.woocommerce-product-gallery__image img')
            if img.get('src')
        ]

        # --- Description courte ---
        desc_el = soup.select_one('.product-short-description')
        if desc_el:
            for br in desc_el.find_all('br'):
                br.replace_with('\n')
            lines = [line.strip() for line in re.sub(r' +', ' ', desc_el.get_text(separator=' ')).split('\n')]
            short_description = '\n'.join(line for line in lines if line)
        else:
            short_description = None

        # --- Description longue ---
        desc_div = soup.select_one('.panel.entry-content.active')
        description = None
        if desc_div:
            for br in desc_div.find_all('br'):
                br.replace_with('\n')
            raw_text = re.sub(r' +', ' ', desc_div.get_text(separator=' '))
            lines = [line.strip() for line in raw_text.split('\n')]
            description_parts = [
                line for line in lines
                if line and line != self.TEXTE_A_EXCLURE
            ]
            description = '\n'.join(description_parts) if description_parts else None
        # --- Fil d'Ariane (breadcrumb) ---
        breadcrumb = [
            a.get_text(strip=True)
            for a in soup.select('nav.woocommerce-breadcrumb a')
        ][1:]  # on exclut "Accueil"

        category      = breadcrumb[0] if len(breadcrumb) > 0 else category_name
        sub_category  = breadcrumb[1] if len(breadcrumb) > 1 else None
        sub_sub_cat   = breadcrumb[2] if len(breadcrumb) > 2 else None

        # Catégories supplémentaires WooCommerce (fusion sans doublon)
        woo_cats = [a.get_text(strip=True) for a in soup.select('span.posted_in a')]
        if sub_sub_cat:
            extra = [c for c in woo_cats if c != sub_sub_cat]
            sub_sub_cat = [sub_sub_cat] + extra if extra else sub_sub_cat
        elif sub_category:
            extra = [c for c in woo_cats if c != sub_category]
            sub_category = [sub_category] + extra if extra else sub_category

        # --- Tags ---
        tags = [a.get_text(strip=True) for a in soup.select('.tagged_as a')]

        # --- Assemblage ---
        info = self.product_info()
        info["name"]                   = name
        info["price_eur"]              = f"{price_eur} €" if price_eur else None
        info["price_fcfa"]             = f"{price_fcfa} FCFA" if price_fcfa else None
        info["short_description"]      = short_description
        info["description"]            = description
        info["list_image_product_url"] = images
        info["category"]               = category
        info["sub_category"]           = sub_category
        info["sub_sub_category"]       = sub_sub_cat
        info["tags"]                   = tags
        info["url_product"]            = url

        self.all_products.append(info)
        print(f"      ✓ {name} | {info['price_fcfa']}")

    # -------------------------------------------------------------------------
    # Sauvegarde JSON
    # -------------------------------------------------------------------------
    def save_json(self, filename="africouleur_products.json"):
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(self.all_products, f, indent=4, ensure_ascii=False)
        print(f"\n[JSON] {len(self.all_products)} produits sauvegardés → {filename}")

    # -------------------------------------------------------------------------
    # Sauvegarde CSV
    # -------------------------------------------------------------------------
    def save_csv(self, filename="africouleur_products.csv"):
        if not self.all_products:
            print("Aucun produit à sauvegarder.")
            return

        fieldnames = [
            "name", "price_eur", "price_fcfa", "short_description", "description",
            "category", "sub_category", "sub_sub_category",
            "tags", "url_product", "list_image_product_url"
        ]

        with open(filename, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for p in self.all_products:
                row = dict(p)
                for key in ("list_image_product_url", "tags", "sub_category", "sub_sub_category"):
                    if isinstance(row[key], list):
                        row[key] = " | ".join(row[key])
                writer.writerow(row)

        print(f"[CSV]  {len(self.all_products)} produits sauvegardés → {filename}")

    # -------------------------------------------------------------------------
    # Lancement
    # -------------------------------------------------------------------------
    def run(self):
        try:
            self.scrape_website()
        finally:
            self.save_json("africouleur_products.json")
            self.save_csv("africouleur_products.csv")
            print(f"\nTerminé. {len(self.all_products)} produits collectés au total.")


if __name__ == "__main__":
    scraper = Africouleur("https://www.africouleur.com")
    scraper.run()