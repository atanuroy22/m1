from . import facebook, instagram, linkedin


def get_platform_module(platform: str):
    value = str(platform or "LinkedIn").strip().lower()
    if value == "facebook":
        return facebook
    if value == "instagram":
        return instagram
    return linkedin

