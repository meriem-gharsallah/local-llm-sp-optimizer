"""
Module de gestion des règles métier pour le prompt LLM
Les règles sont centralisées ici pour faciliter la maintenance
"""

from typing import List, Dict


class PromptRules:
    """
    Gère les règles métier à injecter dans le prompt du LLM
    """
    
    # Règles de base (toujours actives)
    BASE_RULES = [
        "Ne jamais transformer LEFT JOIN en INNER JOIN - cela changerait les résultats",
        "Éviter SELECT * - préférer la liste explicite des colonnes",
        "Ne pas utiliser de fonctions (YEAR, MONTH, UPPER, etc.) sur les colonnes dans WHERE",
        "Ne pas proposer un index qui existe déjà",
        "Préférer EXISTS à IN pour les sous-requêtes",
        "Utiliser WITH (NOLOCK) uniquement si les lectures sales sont acceptables",
        "Éviter les curseurs - préférer les opérations ensemblistes",
        "Ajouter un ORDER BY seulement si nécessaire"
    ]
    
    # Règles spécifiques pour les index
    INDEX_RULES = [
        "Un index sur une colonne de type DATE ou DATETIME est utile pour les recherches par date",
        "Un index couvrant doit contenir toutes les colonnes du SELECT dans INCLUDE",
        "Éviter les indexes sur les colonnes avec faible sélectivité (< 5%)",
        "Ne pas créer plus de 5-6 indexes par table"
    ]
    
    # Règles de performance générales
    PERFORMANCE_RULES = [
        "Les fonctions sur les colonnes empêchent l'utilisation des indexes",
        "BETWEEN est plus efficace que plusieurs conditions OR",
        "Préférer UNION ALL à UNION si les doublons ne sont pas un problème",
        "Éviter les sous-requêtes corrélées quand une jointure est possible"
    ]
    
    # Règles de sécurité
    SECURITY_RULES = [
        "Ne jamais suggérer TRUNCATE TABLE sans WHERE",
        "Ne jamais suggérer DROP TABLE",
        "Faire précéder les modifications de données par BEGIN TRANSACTION"
    ]
    
    @classmethod
    def get_all_rules(cls) -> List[str]:
        """Retourne toutes les règles"""
        return cls.BASE_RULES + cls.INDEX_RULES + cls.PERFORMANCE_RULES + cls.SECURITY_RULES
    
    @classmethod
    def get_rules_for_prompt(cls, categories: List[str] = None) -> str:
        """
        Retourne les règles formatées pour le prompt
        
        Args:
            categories: Liste des catégories à inclure (base, index, performance, security)
                       Si None, inclut toutes les règles
        
        Returns:
            Texte formaté des règles
        """
        all_categories = {
            "base": cls.BASE_RULES,
            "index": cls.INDEX_RULES,
            "performance": cls.PERFORMANCE_RULES,
            "security": cls.SECURITY_RULES
        }
        
        if categories:
            rules_to_include = []
            for cat in categories:
                if cat in all_categories:
                    rules_to_include.extend(all_categories[cat])
        else:
            rules_to_include = cls.get_all_rules()
        
        # Formater les règles pour le prompt
        rules_text = "REGLES A RESPECTER :\n"
        for i, rule in enumerate(rules_to_include, 1):
            rules_text += f"{i}. {rule}\n"
        
        return rules_text
    
    @classmethod
    def add_custom_rule(cls, rule: str, category: str = "base"):
        """
        Ajoute une règle personnalisée (peut être chargée depuis un fichier)
        
        Args:
            rule: La règle à ajouter
            category: Catégorie (base, index, performance, security)
        """
        if category == "base":
            cls.BASE_RULES.append(rule)
        elif category == "index":
            cls.INDEX_RULES.append(rule)
        elif category == "performance":
            cls.PERFORMANCE_RULES.append(rule)
        elif category == "security":
            cls.SECURITY_RULES.append(rule)
    
    @classmethod
    def load_from_file(cls, file_path: str):
        """
        Charge des règles supplémentaires depuis un fichier texte
        
        Args:
            file_path: Chemin vers le fichier de règles (une règle par ligne)
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        cls.BASE_RULES.append(line)
        except FileNotFoundError:
            print(f"Fichier de règles non trouvé: {file_path}")


# Fonctions simplifiées pour l'utilisation dans l'analyseur LLM
def get_rules_text(categories: List[str] = None) -> str:
    """
    Retourne les règles formatées pour le prompt
    
    Args:
        categories: Liste des catégories à inclure
    
    Returns:
        Texte formaté des règles
    """
    return PromptRules.get_rules_for_prompt(categories)


def get_base_rules() -> List[str]:
    """Retourne les règles de base"""
    return PromptRules.BASE_RULES


def get_index_rules() -> List[str]:
    """Retourne les règles sur les indexes"""
    return PromptRules.INDEX_RULES


def get_performance_rules() -> List[str]:
    """Retourne les règles de performance"""
    return PromptRules.PERFORMANCE_RULES


def get_security_rules() -> List[str]:
    """Retourne les règles de sécurité"""
    return PromptRules.SECURITY_RULES


def get_all_rules() -> List[str]:
    """Retourne toutes les règles"""
    return PromptRules.get_all_rules()