"""
utils/embeds.py — Consistent Discord embed builder with enhanced UI.
"""

from datetime import datetime, timezone
from typing import Optional, List, Tuple

import discord


class EmbedBuilder:
    """
    Builds consistent, visually appealing Discord embeds.
    
    All embeds share common styling: timestamp, footer, and color scheme.
    """

    COLORS = {
        "success":  0x2ECC71,  # Green
        "error":    0xE74C3C,  # Red
        "warning":  0xF39C12,  # Orange/Yellow
        "info":     0x3498DB,  # Blue
        "farming":  0x9B59B6,  # Purple
        "account":  0x1ABC9C,  # Teal
        "config":   0x34495E,  # Dark gray-blue
        "neutral":  0x7289DA,  # Discord blurple
    }

    FOOTER_TEXT = "LanguageNut Bot"
    FOOTER_ICON = None

    @classmethod
    def _base(cls, color: int = 0x7289DA) -> discord.Embed:
        """Create base embed with consistent footer and timestamp."""
        embed = discord.Embed(
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(
            text=cls.FOOTER_TEXT,
            icon_url=cls.FOOTER_ICON,
        )
        return embed

    # ------------------------------------------------------------------
    # Status Embeds
    # ------------------------------------------------------------------

    @classmethod
    def success(cls, title: str, description: str, **kwargs) -> discord.Embed:
        """Green success embed."""
        embed = cls._base(cls.COLORS["success"])
        embed.title = f"✅ {title}"
        embed.description = description
        return cls._add_fields(embed, kwargs)

    @classmethod
    def error(cls, title: str, description: str, **kwargs) -> discord.Embed:
        """Red error embed."""
        embed = cls._base(cls.COLORS["error"])
        embed.title = f"❌ {title}"
        embed.description = description
        return cls._add_fields(embed, kwargs)

    @classmethod
    def warning(cls, title: str, description: str, **kwargs) -> discord.Embed:
        """Orange warning embed."""
        embed = cls._base(cls.COLORS["warning"])
        embed.title = f"⚠️ {title}"
        embed.description = description
        return cls._add_fields(embed, kwargs)

    @classmethod
    def info(cls, title: str, description: str, **kwargs) -> discord.Embed:
        """Blue info embed."""
        embed = cls._base(cls.COLORS["info"])
        embed.title = f"ℹ️ {title}"
        embed.description = description
        return cls._add_fields(embed, kwargs)

    # ------------------------------------------------------------------
    # Farming Embeds
    # ------------------------------------------------------------------

    @classmethod
    def farming_start(cls, account: str, tasks: int, **kwargs) -> discord.Embed:
        """Farming session started."""
        embed = cls._base(cls.COLORS["farming"])
        embed.title = "🌾 Farming Session Started"
        embed.description = f"Account: **{account}**\nTasks: **{tasks}**"
        return cls._add_fields(embed, kwargs)

    @classmethod
    def farming_progress(cls, account: str, completed: int, total: int, **kwargs) -> discord.Embed:
        """Farming progress with progress bar."""
        embed = cls._base(cls.COLORS["farming"])
        embed.title = "🌾 Farming in Progress"
        
        # Progress bar
        pct = completed / total if total > 0 else 0
        bar = cls._progress_bar(pct)
        
        embed.description = (
            f"Account: **{account}**\n"
            f"Progress: **{completed}/{total}**\n"
            f"{bar}"
        )
        return cls._add_fields(embed, kwargs)

    @classmethod
    def farming_complete(cls, account: str, stats: dict, **kwargs) -> discord.Embed:
        """Farming session complete with stats."""
        embed = cls._base(cls.COLORS["success"])
        embed.title = "✅ Farming Complete"
        
        desc = f"Account: **{account}**\n"
        if stats:
            desc += (
                f"Tasks completed: **{stats.get('completed', 0)}**\n"
                f"XP earned: **{stats.get('xp', 0):,}**\n"
                f"Duration: **{stats.get('duration', 'N/A')}**\n"
                f"Accuracy: **{stats.get('accuracy', 'N/A')}%**\n"
            )
        embed.description = desc
        return cls._add_fields(embed, kwargs)

    # ------------------------------------------------------------------
    # Account Embeds
    # ------------------------------------------------------------------

    @classmethod
    def account_added(cls, username: str, **kwargs) -> discord.Embed:
        """Account added successfully."""
        embed = cls._base(cls.COLORS["account"])
        embed.title = "👤 Account Added"
        embed.description = f"Username: **{username}**\nStatus: ✅ Active"
        return cls._add_fields(embed, kwargs)

    @classmethod
    def account_blocked(cls, username: str, **kwargs) -> discord.Embed:
        """Account blocked/suspended."""
        embed = cls._base(cls.COLORS["error"])
        embed.title = "⛔ Account Suspended"
        embed.description = (
            f"Account: **{username}**\n\n"
            f"This account has been permanently blocked by LanguageNut's anti-cheat system.\n\n"
            f"**Suggested actions:**\n"
            f"• Try logging in via web browser\n"
            f"• Contact support at support@languagenut.com\n"
            f"• The account may need an administrator reset"
        )
        return cls._add_fields(embed, kwargs)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @classmethod
    def _progress_bar(cls, fraction: float, length: int = 12) -> str:
        """Create a text-based progress bar."""
        filled = round(fraction * length)
        filled = max(0, min(length, filled))
        empty = length - filled
        bar = "█" * filled + "░" * empty
        pct = round(fraction * 100)
        return f"`{bar}` **{pct}%**"

    @classmethod
    def _add_fields(cls, embed: discord.Embed, kwargs: dict) -> discord.Embed:
        """Add fields from kwargs if provided."""
        fields = kwargs.pop("fields", None)
        if fields:
            for name, value, inline in fields:
                embed.add_field(name=name, value=value, inline=inline)
        
        # Add thumbnail if provided
        thumbnail = kwargs.pop("thumbnail", None)
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        
        # Add image if provided
        image = kwargs.pop("image", None)
        if image:
            embed.set_image(url=image)
        
        # Add author if provided
        author = kwargs.pop("author", None)
        if author:
            embed.set_author(**author)

        return embed
