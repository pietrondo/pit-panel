"""String utilities for the pit-panel core."""


def truncate_string(text: str, max_length: int = 50) -> str:
    """
    Truncate a string to a maximum length, appending an ellipsis if necessary.

    Args:
        text (str): The string to truncate.
        max_length (int): The maximum length of the output string, including the ellipsis.

    Returns:
        str: The truncated string.
    """
    if len(text) <= max_length:
        return text

    if max_length <= 3:
        return "." * max_length

    return text[: max_length - 3] + "..."
