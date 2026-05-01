def calories_from_macros(protein_g: float, fat_g: float, carbs_g: float) -> int:
    """Calculate calories from protein, fat, and carbs."""
    return round(protein_g * 4 + fat_g * 9 + carbs_g * 4)
