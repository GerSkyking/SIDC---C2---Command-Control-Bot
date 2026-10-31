from .c2bridge import C2Bridge


async def setup(bot):
    await bot.add_cog(C2Bridge(bot))
