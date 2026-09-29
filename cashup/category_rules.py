"""Guess a stock category from an item name (invoice lines, sales mix, new items).

Rules are tried in order and the first match wins, so specific phrases must come
before the general words they contain (e.g. "ginger ale" before "ginger").
"""
import re

_RULES: list[tuple[str, str]] = [
    # --- specific phrases that would otherwise be caught by a broader rule ---
    ('Other Costs', r'^\s*other\s*cost'),
    ('Soft Drinks', r'coconut\s*water|bitter\s*lemon|ginger\s*(ale|beer)|fruit\s*punch|\bmineral\b'
                    r'|cranberry'),
    ('Mixers', r'(simple|sugar|gomme)\s*syrup'),
    ('Long Life', r'fish\s*sauce|coconut\s*(milk|cream)|\btin(ned)?\b|canned|condens|evaporat|\buht\b|long\s*life|essence'),
    ('Spirits', r'coffee\s*rum|\brum\b'),
    ('Coffee & Tea', r'infusion'),

    # --- drinks ---
    ('Water', r'\bwater\b|blu\s*pura|perrier|evian|pellegrino|acqua'),
    ('Cider', r'\bcider\b|slow\s*t\w*tle'),
    ('Beer', r'\bbeer\b|\blager\b|\bale\b|\bstout\b|draught|\bkeg\b|seybrew|setbrew|\beku\b'
             r'|guin+es+|heineken|castle|corona|stella|budweiser|carlsberg'),
    ('Sparkling Wine', r'prosecco|champagne|\bbrut\b|mo[eë]t|\bmoed\b|veuve|cli[cq]+uo?t'
                       r'|\bcava\b|cr[eé]mant|sparkling\s*wine|lamberti'),
    ('Liqueurs', r'liqueur|baileys|kahlua|amaretto|disaronno|limonc|martini|vermouth|sambuca'
                 r'|frangelico|j[aä]germeister|marie\s*brizard|creme\s*de|malibu|drambuie|galliano'),
    ('Spirits', r'vodka|\bgin\b|\brhum\b|whisk(e)?y|bourbon|scotch|tequila|mezcal|cognac|brandy'
                r'|\bvsop\b|\bxo\b|absolut|smirnoff|belvedere|beefeater|bombay|sapphire|gordon'
                r'|hendrick|seygin|jameson|jack\s*daniel|chivas|olmeca|patron|takamaka|appleton'
                r'|st\.?\s*remy|aperol|campari|cointreau|triple\s*sec|cura[cçs]ao|st\.?\s*germain'
                r'|angostura|\bbitters?\b|\bl\'?or\b|bacardi|havana|captain\s*morgan|kraken'
                r'|johnnie|glenfiddich|jose\s*cuervo|tanqueray|grey\s*goose|ketel|hennessy'),
    ('Wine', r'^\s*(19|20)\d{2}\b|\bwine\b|\bros[eé]\b|sauvignon|pinot|chardonnay|merlot|cabernet'
             r'|shiraz|syrah|chablis|sancerre|provence|chateau|bardolino|chiaretto|riesling|malbec'
             r'|grig[ie]o|mourv[eè]dre|cinsault|porcupine|false\s*bay|kleine\s*zalze|bouchard'
             r'|torre\s*del|minuty|miraval|collio|chianti|rioja|prestige'),
    ('Soft Drinks', r'coca|\bcoke\b|pepsi|fanta|sprite|7\s*up|\btonic\b|\bsoda\b|schweppes'
                    r'|red\s*bull|cordial|grenadine|orgeat|\bsyrup\b|\bstrup\b|\bcola\b'),
    ('Juices', r'juice|pur[eé]e|nectar'),
    ('Coffee & Tea', r'coffee|espresso|ristretto|lungo|decaf|macchiato|mocha|cappuc+ino|\blatte\b|americano|\bbeans?\b|filtro'
                     r'|\btea\b|earl\s*grey|english\s*breakfast|chamomile'),

    # --- food ---
    ('Bakery', r'\bbuns?\b|bread|tortilla|baguette|\bpita\b|croissant|brioche'),
    ('Dairy & Eggs', r'\beggs?\b|\bmilk\b|cream|yog(h)?urt|yourget|butter|chees|chedd|mozzarella|parmi|pamasan'
                     r'|parmesan|cheddar|feta'),
    ('Herbs', r'\bmint\b|basil|cor+iander(?!\s*seed)|cilantro|\bherbs?\b|parsley|rosemary|thyme|\bdill\b|lemon\s*grass'
              r'|curry\s*lea|chives|oregano|\bsage\b|tarragon'),
    ('Frozen', r'french\s*fries|frozen'),
    ('Seafood', r'\bfish\b|seafood|prawn|shrimp|tuna|salmon|octopus|squid|calamari|lobster|crab|mussel|anchov'
                r'|job\s*fish|red\s*snapper|grouper'),
    ('Poultry', r'chicken|\bduck\b|turkey'),
    ('Meat', r'\bbeef\b|\bpork\b|\blamb\b|bacon|\bham\b|sausage|mince|steak|\bveal\b'),
    ('Vegetables', r'cabbage|cucumber|lettuce|tomato|onion|garlic|potato|carrot|capsicum'
                   r'|bell\s*pepper|zucchini|courgette|eggplant|aubergine|spinach|broccoli'
                   r'|cauliflower|celery|mushroom|chil+i(e)?\s*fresh|fresh\s*chil+i|pum?p?kin|\bginger\b(?!\s*pickle)|avocado|rocket|arugula'),
    ('Fruit', r'banana|mango|orange|orenge|papaya|pas+ion|pin(e)?apple|strawberr|\blimes?\b|lemons?\b'
              r'|\bapples?\b|melon|grape|kiwi|berr(y|ies)|coconut\b(?!\s*powder)'),
    ('Spices', r'cinnamon|pepper|cumin|turmeric|paprika|nutmeg|clove|cardamo|star\s*anis|staran'
               r'|chil+i\w*\s*(powder|crushed|flakes)|powder\s*chil+i|curry\s*powder|masala|\bseeds?\b|\bsalt\b|sugar|honey|coconut\s*powder|vanilla|wasabi'),
    ('Oils & Vinegars', r'\boil\b|\boli\b|olive\s*oil|extra\s*virgin|vinegar'),
    ('Sauces & Condiments', r'sauce|ketchup|mayonnaise|mustard|musted|dijon|pesto|tahini|kikkoman'
                            r'|\bsoya?\b|capers|\bolives\b|pickle'),
    ('Long Life', r'flour|\boats?\b|oat\s*meal|cashew|almond|peanut|\bnuts?\b|\brice\b|pasta'
                  r'|noodle|canned|tinned|\btin\b|chickpea|lentil|yeast|chocolat|wakame|spag\w*t+i|bread\s*crumb|panko'),
    ('Cleaning', r'detergent|bleach|\bsoap\b|sanitiz|degreas|dish\s*wash|cleaner|chlorine|\bmop\b'
                 r'|sponge|bin\s*liner|garbage\s*bag|toilet\s*(paper|roll)'),
    ('Packaging', r'\bstraws?\b|napkin|take\s*away|container|\bcups?\b|\blids?\b|\bfoil\b'
                  r'|cling\s*(film|wrap)|paper\s*bag'),
]

_COMPILED = [(category, re.compile(pattern, re.IGNORECASE)) for category, pattern in _RULES]

# Made drinks on a sales mix are not stock, so don't file them under an ingredient.
_MADE_DRINK = re.compile(
    r'mocktail|cocktail|mojito|daiquiri|margarita|colada|spritz|caipi|sangria|shirl(e)?y\s*temple'
    r'|sunset|sunrise|cuba\s*libr|long\s*island|cosmopolitan|pi[nñ]a\b',
    re.IGNORECASE,
)


# Menu dishes on a sales mix ("FISH CURRY", "CHICKEN BURGER") must not be filed as the ingredient.
_MENU_DISH = re.compile(
    r'burger|\bwraps?\b|curry|salad|chips|fries|carpaccio|ceviche|fingers|kofta|baguette|\bbowl\b'
    r'|tataki|sas?hs?imi|tenders?\b|wings|kebab|sandwich|omelet|scrambled|platter|\bplat\b|\btart\b'
    r'|nougat|ganache|braised|cake|brownie|tiramisu|\bpasta\b|napol|garlic\s*bread|(?<!english\s)breakfast'
    r'|^\s*add\b|supplement|\bmenu\b|sorbet|ice\s*cream|smoothie|milkshake|olada|hummus|grilled|risotto'
    r'|pizza|\bsoup\b|toast|\bclub\b|\bsides?\b|fresh\s*fruit(?!\s*(juice|punch))|\bcatch\b|basket|\bkids?\b|garlic\s*prawn'
    r'|\bfor\s+(one|two|\d+)\b|\brice\b|\bdhal+\b|lentils|\bveg\b',
    re.IGNORECASE,
)


def guess_category(name: str | None, menu_item: bool = False) -> str | None:
    """Category for an item name, or None if no rule matches.

    menu_item=True for POS sales mix names, where dishes and made drinks get no category.
    """
    text = ' '.join((name or '').split())
    if not text or (_MADE_DRINK.search(text) and not re.search(r'juice', text, re.IGNORECASE)):
        return None
    if menu_item and _MENU_DISH.search(text):
        return None
    for category, pattern in _COMPILED:
        if pattern.search(text):
            return category
    return None
