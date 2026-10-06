import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta

import discord
from discord import app_commands
from dotenv import load_dotenv

import dorm_menu
import weather
from main import (
    BASE_DIR, FETCH_COUNT, fetch_contests, get_setting, init_db,
    load_all_contests, set_setting,
)

# .env 파일에서 설정 읽기 (실행 위치와 상관없이 bot.py 옆의 .env 사용)
load_dotenv(BASE_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("contest_bot")


def require_env(name):
    value = os.getenv(name)
    if not value:
        log.error(f"환경변수 {name}가 설정되지 않았습니다. .env 파일을 확인하세요.")
        sys.exit(1)
    return value


TOKEN = require_env("DISCORD_TOKEN")
GUILD_ID = int(require_env("GUILD_ID"))

# 자동 알림을 보낼 기본 Discord 채널 ID (선택)
# /공모전설정, /식단설정으로 채널을 지정하면 그 채널이 우선 사용된다
CHANNEL_ID = int(os.getenv("CHANNEL_ID") or 0) or None

# 자동 알림 채널을 settings 테이블에 저장할 때 쓰는 키
CONTEST_CHANNEL_KEY = "contest_channel"
MENU_CHANNEL_KEY = "menu_channel"
WEATHER_CHANNEL_KEY = "weather_channel"
WEATHER_LOCATION_KEY = "weather_location"  # 아침 알림에 쓸 기상청 지역 코드

# 서버 시간대(보통 UTC)와 상관없이 한국 시간 기준으로 동작
KST = dorm_menu.KST
RUN_HOURS = [3, 9, 15, 21]
MENU_HOURS = [8]        # 오늘의 식단을 보낼 시각 (KST)
MENU_RETRY_COUNT = 3    # 식단 사이트 접속 실패 시 시도 횟수
MENU_RETRY_DELAY = 300  # 재시도 간격 (초)

PAGE_SIZE = 4         # 한 페이지에 보여줄 공모전 수
VIEW_TIMEOUT = 600    # 좌우 넘기기 버튼이 동작하는 시간 (초)

client = discord.Client(intents=discord.Intents.default())
tree = app_commands.CommandTree(client)

guild = discord.Object(id=GUILD_ID)


def get_alert_channel(key):
    """
    자동 알림을 보낼 채널을 찾는다.
    명령어로 설정한 채널이 없으면 .env의 CHANNEL_ID를 사용한다.
    찾지 못하면 None
    """

    channel_id = get_setting(key) or CHANNEL_ID
    if not channel_id:
        return None
    return client.get_channel(int(channel_id))


def make_contest_embed(contest, is_new=False):
    """
    공모전 하나를 디스코드 임베드(박스)로 만든다.
    contest: id, title, dday, organization, poster_url 키를 가진 dict
    is_new: 새로 발견된 공모전이면 초록색 + NEW 표시
    """

    prefix = "🆕" if is_new else "📌"

    embed = discord.Embed(
        title=f"{prefix} {contest['title']}"[:256],  # 임베드 제목은 최대 256자
        url=f"https://allforyoung.com/posts/{contest['id']}",
        color=discord.Color.green() if is_new else discord.Color.blue()
    )
    embed.add_field(
        name="🏢 주최",
        value=contest.get("organization") or "정보 없음",
        inline=False
    )
    embed.add_field(
        name="⏰ 접수 기간",
        value=f"`{contest.get('dday') or '정보 없음'}`",
        inline=False
    )

    # 원본 포스터(평균 1.4MB)는 디스코드가 불러오는 데 오래 걸려서
    # 가벼운 썸네일(평균 200KB대 webp)을 우선 사용
    image_url = contest.get("thumbnail_url") or contest.get("poster_url")
    if image_url:
        embed.set_thumbnail(url=image_url)

    return embed


class ContestPager(discord.ui.View):
    """
    공모전을 한 페이지에 PAGE_SIZE개씩 보여주고 ◀ ▶ 버튼으로 넘기는 화면.
    명령어를 실행한 사람만 넘길 수 있다.
    """

    def __init__(self, owner_id, header, contests, new_ids=frozenset()):
        super().__init__(timeout=VIEW_TIMEOUT)
        self.owner_id = owner_id
        self.header = header

        # 임베드는 미리 한 번만 만들어 두고 페이지 단위로 묶음
        embeds = [
            make_contest_embed(contest, contest["id"] in new_ids)
            for contest in contests
        ]
        self.pages = [
            embeds[i:i + PAGE_SIZE]
            for i in range(0, len(embeds), PAGE_SIZE)
        ]

        self.index = 0
        self.message = None
        self.update_buttons()

    def update_buttons(self):
        self.page_button.label = f"{self.index + 1} / {len(self.pages)}"

        # 한 페이지뿐이면 넘길 필요가 없으므로 버튼 비활성화
        only_one = len(self.pages) <= 1
        self.prev_button.disabled = only_one
        self.next_button.disabled = only_one

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "명령어를 직접 입력해서 확인해 주세요. 🙂",
                ephemeral=True
            )
            return False
        return True

    async def show_page(self, interaction: discord.Interaction):
        self.update_buttons()
        await interaction.response.edit_message(
            embeds=self.pages[self.index],
            view=self
        )

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 첫 장에서 누르면 마지막 장으로
        self.index = (self.index - 1) % len(self.pages)
        await self.show_page(interaction)

    @discord.ui.button(label="1 / 1", style=discord.ButtonStyle.primary, disabled=True)
    async def page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass  # 현재 페이지 표시용

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 마지막 장에서 누르면 첫 장으로
        self.index = (self.index + 1) % len(self.pages)
        await self.show_page(interaction)

    async def on_timeout(self):
        # 시간이 지나면 버튼을 비활성화해서 눌러도 반응이 없다는 걸 표시
        self.prev_button.disabled = True
        self.next_button.disabled = True

        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def send(self, interaction: discord.Interaction):
        self.message = await interaction.followup.send(
            content=self.header,
            embeds=self.pages[self.index],
            view=self,
            wait=True
        )


async def send_contest_embeds(send, header, contests):
    """
    공모전 목록을 임베드로 전송한다.
    send: interaction.followup.send 또는 channel.send
    """

    embeds = [make_contest_embed(contest) for contest in contests]

    # 메시지 하나에 임베드는 최대 10개까지만 보낼 수 있어서 나눠서 전송
    for i in range(0, len(embeds), 10):
        content = header if i == 0 else None
        await send(content=content, embeds=embeds[i:i + 10])


@client.event
async def on_ready():

    log.info(f"로그인 성공: {client.user}")

    # on_ready는 재연결될 때마다 다시 호출되므로 최초 1회만 실행
    if not hasattr(client, "automatic_check_started"):
        client.automatic_check_started = True

        await tree.sync(guild=guild)
        log.info("Slash Command 동기화 완료")

        # 지역 목록은 처음 한 번만 기상청에서 받아 파일에 저장 (자동완성에 필요)
        asyncio.create_task(preload_zones())
        asyncio.create_task(automatic_check())
        asyncio.create_task(automatic_menu())


@tree.command(
    name="공모전",
    description=f"최신 공모전 {FETCH_COUNT}개를 갱신한 뒤 저장된 공모전을 모두 보여줍니다.",
    guild=guild
)
async def contest(interaction: discord.Interaction):

    await interaction.response.defer()

    # 1) 최신 공모전 갱신
    new_contests = []
    update_failed = False

    try:
        # 네트워크 요청이 봇 전체를 멈추지 않도록 별도 스레드에서 실행
        _, new_contests = await asyncio.to_thread(fetch_contests)
    except Exception:
        # 갱신에 실패해도 DB에 저장된 목록은 보여줌
        log.exception("/공모전 갱신 중 오류")
        update_failed = True

    # 2) DB에 있는 공모전 모두 출력
    contests = load_all_contests()

    if not contests:
        message = "📢 등록된 공모전이 없습니다."
        if update_failed:
            message = "❌ 공모전을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."
        await interaction.followup.send(message)
        return

    header = f"📋 **공모전 목록** ({len(contests)}개)"
    if new_contests:
        header += f" · 🆕 새로 등록 {len(new_contests)}개"
    if update_failed:
        header += "\n⚠️ 최신 정보 갱신에 실패해서 저장된 목록만 보여드립니다."

    pager = ContestPager(
        interaction.user.id,
        header,
        contests,
        new_ids={contest["id"] for contest in new_contests}
    )
    await pager.send(interaction)


async def set_alert_channel(interaction, key, channel, label):
    """
    /공모전설정, /식단설정 공통 처리
    """

    # 봇이 그 채널에 메시지를 보낼 수 있는지 먼저 확인
    permissions = channel.permissions_for(interaction.guild.me)
    if not (permissions.view_channel and permissions.send_messages and permissions.embed_links):
        await interaction.response.send_message(
            f"❌ 봇이 {channel.mention} 채널에 메시지(임베드)를 보낼 권한이 없습니다. 채널 권한을 확인해 주세요.",
            ephemeral=True
        )
        return

    set_setting(key, channel.id)
    log.info(f"{label} 알림 채널 설정: #{channel.name} ({channel.id}) by {interaction.user}")

    await interaction.response.send_message(
        f"✅ 이제 {label} 알림을 {channel.mention} 채널로 보냅니다."
    )


@tree.command(
    name="공모전설정",
    description="새 공모전 자동 알림을 보낼 채널을 설정합니다.",
    guild=guild
)
@app_commands.describe(채널이름="공모전 알림을 받을 채널")
@app_commands.default_permissions(manage_guild=True)
async def set_contest_channel(interaction: discord.Interaction, 채널이름: discord.TextChannel):
    await set_alert_channel(interaction, CONTEST_CHANNEL_KEY, 채널이름, "공모전")


@tree.command(
    name="식단설정",
    description="오늘의 식단 자동 알림을 보낼 채널을 설정합니다.",
    guild=guild
)
@app_commands.describe(채널이름="식단 알림을 받을 채널")
@app_commands.default_permissions(manage_guild=True)
async def set_menu_channel(interaction: discord.Interaction, 채널이름: discord.TextChannel):
    await set_alert_channel(interaction, MENU_CHANNEL_KEY, 채널이름, "식단")


WEEKDAYS = "월화수목금토일"
EMBED_CHAR_LIMIT = 5500  # 임베드 하나의 전체 글자 수 제한(6000)보다 여유 있게


# 점심과 저녁 열 사이 간격 (탭 1.5개 정도)
# 디스코드는 일반 공백/탭을 지워 버리므로 전각 공백(em space)을 사용하고,
# 첫 줄 앞 공백도 잘리지 않도록 맨 앞에 폭 없는 문자(zero-width space)를 둔다
MEAL_GAP = "​  "
DINNER_TITLE = f"{MEAL_GAP}🌙 저녁"


def format_meal(items, indent=""):
    lines = items or [dorm_menu.NONE_TEXT]
    return "\n".join(f"{indent}{line}" for line in lines)


def day_label(day):
    return f"{day:%m/%d} ({WEEKDAYS[day.weekday()]})"


def make_week_menu_embeds(week, today):
    """
    일주일 식단을 날짜 | 점심 | 저녁 3열 표 형태의 임베드로 만든다.
    글자 수가 많으면 여러 임베드로 나눈다.
    """

    embeds = []
    embed = None

    for day in sorted(week):
        menu = week[day]
        date_text = f"**{day_label(day)}**"
        if day == today:
            date_text += "\n👉 오늘"

        row = [
            ("📅 날짜", date_text),
            ("🍚 점심", format_meal(menu["점심"])),
            (DINNER_TITLE, format_meal(menu["저녁"], MEAL_GAP)),
        ]
        row_size = sum(len(name) + len(value) for name, value in row)

        if embed is None or len(embed) + row_size > EMBED_CHAR_LIMIT or len(embed.fields) + 3 > 25:
            embed = discord.Embed(color=discord.Color.orange())
            embeds.append(embed)

        for name, value in row:
            embed.add_field(name=name, value=value, inline=True)

    first, last = min(week), max(week)
    embeds[0].title = f"🍱 기숙사 주간 식단 ({day_label(first)} ~ {day_label(last)})"
    embeds[-1].set_footer(text="식자재 수급현황에 따라 메뉴가 변경될 수 있습니다.")

    return embeds


def make_day_menu_embed(day, menu):
    """
    하루 식단을 점심 | 저녁 2열 표 형태의 임베드로 만든다.
    """

    embed = discord.Embed(
        title=f"🍱 오늘의 기숙사 식단 · {day_label(day)}",
        color=discord.Color.orange()
    )
    embed.add_field(name="🍚 점심", value=format_meal(menu["점심"]), inline=True)
    embed.add_field(name=DINNER_TITLE, value=format_meal(menu["저녁"], MEAL_GAP), inline=True)
    embed.set_footer(text="식자재 수급현황에 따라 메뉴가 변경될 수 있습니다.")

    return embed


async def fetch_menu(interaction, label, getter, today):
    """
    /식단, /오늘 공통 처리: 응답을 미루고 식단을 가져온다.
    실패하면 안내 메시지를 보내고 None을 반환한다.
    """

    await interaction.response.defer()

    try:
        return await asyncio.to_thread(getter, today)
    except Exception:
        log.exception(f"{label} 조회 중 오류")
        await interaction.followup.send("❌ 식단을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
        return None


@tree.command(
    name="식단",
    description="이번 주 기숙사 식단(점심/저녁)을 보여줍니다.",
    guild=guild
)
async def week_menu(interaction: discord.Interaction):

    today = datetime.now(KST).date()
    week = await fetch_menu(interaction, "/식단", dorm_menu.get_week_menu, today)

    if week is None:
        return

    if not week:
        await interaction.followup.send("🍱 이번 주 식단이 아직 등록되지 않았습니다.")
        return

    await interaction.followup.send(embeds=make_week_menu_embeds(week, today))


@tree.command(
    name="오늘",
    description="오늘의 기숙사 식단(점심/저녁)을 보여줍니다.",
    guild=guild
)
async def today_menu(interaction: discord.Interaction):

    today = datetime.now(KST).date()
    menu = await fetch_menu(interaction, "/오늘", dorm_menu.get_menu, today)

    if menu is not None:
        await interaction.followup.send(embed=make_day_menu_embed(today, menu))


async def preload_zones():
    try:
        await asyncio.to_thread(weather.load_zones)
        log.info("날씨 지역 목록 준비 완료")
    except Exception:
        log.exception("날씨 지역 목록 준비 오류 (첫 /날씨 사용 시 다시 시도)")


def make_weather_embed(name, day, rows):
    """시간대별 inline 필드(날씨/기온/체감) + 기온·체감온도 그래프 임베드를 만든다."""

    def degree(value):
        return "-" if value is None else f"{value}℃"

    temps = [row["temp"] for row in rows if row["temp"] is not None]
    summary = f"🔺 최고 {max(temps)}℃ · 🔻 최저 {min(temps)}℃" if temps else ""

    embed = discord.Embed(
        title=f"🌤️ {name} 날씨 · {day_label(day)}",
        description=f"## {summary}\n\n### {weather.format_flow(rows)}\n​",
        color=discord.Color.teal()
    )

    # 시간대별 카드 (한 줄에 3개씩)
    for row in rows:
        embed.add_field(
            name=weather.clock_label(row["time"]),
            # 짧게 써야 3칸이 한 줄에 들어간다 (길면 아래 줄로 밀림)
            value=(
                f"### {weather.sky_emoji(row['sky'])} {row['sky']}\n\n"
                f"**🌡️ {degree(row['temp'])}**\n\n"
                f"**🥶 {degree(row['feel'])}**\n​"
            ),
            inline=True,
        )

    # 그래프
    embed.add_field(
        name="📈 기온 변화",
        value=f"```\n{weather.format_graph(rows, 'temp')}\n```",
        inline=False,
    )
    embed.add_field(
        name="📉 체감온도 변화",
        value=f"```\n{weather.format_graph(rows, 'feel')}\n```",
        inline=False,
    )
    embed.set_footer(text="출처: 기상청 날씨누리 · 동네예보 (3시간 간격)")

    return embed


async def build_weather_embed(zone):
    """
    지역의 오늘 날씨 임베드를 만든다. 예보가 없으면 None
    실패하면 예외를 그대로 던진다.
    """

    today = datetime.now(KST).date()
    rows = await asyncio.to_thread(weather.get_day_weather, zone["code"], today)
    if not rows:
        return None
    return make_weather_embed(zone["name"], today, rows)


async def zone_autocomplete(interaction: discord.Interaction, current: str):
    # 자동완성은 3초 안에 답해야 해서 목록이 준비되지 않았으면 비워 둠
    if not weather.zones_loaded():
        return []
    return [
        app_commands.Choice(name=zone["name"][:100], value=zone["name"][:100])
        for zone in weather.search_zones(current)
    ]


@tree.command(
    name="날씨",
    description="지역의 오늘 하루 날씨(09시~24시)를 보여줍니다.",
    guild=guild
)
@app_commands.describe(위치="예: 상도동, 서울 동작구 (목록에서 고르면 정확해요)")
@app_commands.autocomplete(위치=zone_autocomplete)
async def weather_command(interaction: discord.Interaction, 위치: str):

    await interaction.response.defer()

    try:
        zone = await asyncio.to_thread(weather.find_zone, 위치)
        if zone is None:
            await interaction.followup.send(f"❌ '{위치}' 지역을 찾지 못했습니다. 동네 이름(예: 상도동)으로 다시 입력해 주세요.")
            return

        embed = await build_weather_embed(zone)
    except Exception:
        log.exception("/날씨 조회 중 오류")
        await interaction.followup.send("❌ 날씨를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
        return

    if embed is None:
        await interaction.followup.send(f"🌤️ {zone['name']}의 오늘 예보가 아직 없습니다.")
        return

    await interaction.followup.send(embed=embed)


@tree.command(
    name="위치설정",
    description="아침 8시 식단과 함께 보낼 날씨의 위치를 설정합니다.",
    guild=guild
)
@app_commands.describe(위치="예: 상도동, 서울 동작구 (목록에서 고르면 정확해요)")
@app_commands.autocomplete(위치=zone_autocomplete)
@app_commands.default_permissions(manage_guild=True)
async def set_weather_location(interaction: discord.Interaction, 위치: str):

    await interaction.response.defer()

    try:
        zone = await asyncio.to_thread(weather.find_zone, 위치)
    except Exception:
        log.exception("/위치설정 지역 검색 중 오류")
        await interaction.followup.send("❌ 지역 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
        return

    if zone is None:
        await interaction.followup.send(f"❌ '{위치}' 지역을 찾지 못했습니다. 동네 이름(예: 상도동)으로 다시 입력해 주세요.")
        return

    set_setting(WEATHER_LOCATION_KEY, zone["code"])
    log.info(f"날씨 위치 설정: {zone['name']} ({zone['code']}) by {interaction.user}")

    await interaction.followup.send(f"✅ 이제 아침 날씨를 **{zone['name']}** 기준으로 보냅니다.")


@tree.command(
    name="날씨설정",
    description="아침 날씨 자동 알림을 보낼 채널을 설정합니다.",
    guild=guild
)
@app_commands.describe(채널이름="날씨 알림을 받을 채널")
@app_commands.default_permissions(manage_guild=True)
async def set_weather_channel(interaction: discord.Interaction, 채널이름: discord.TextChannel):
    await set_alert_channel(interaction, WEATHER_CHANNEL_KEY, 채널이름, "날씨")


def next_run_time(now, hours=RUN_HOURS):
    today = now.replace(minute=0, second=0, microsecond=0)

    for hour in hours:
        candidate = today.replace(hour=hour)

        if candidate > now:
            return candidate

    return today.replace(hour=hours[0]) + timedelta(days=1)


async def sleep_until_next(hours, label):
    """다음 실행 시각(한국 시간 기준)까지 대기한다."""

    now = datetime.now(KST)
    next_run = next_run_time(now, hours)
    wait_seconds = (next_run - now).total_seconds()

    log.info(f"{label}: {next_run:%Y-%m-%d %H:%M} (KST), {wait_seconds / 3600:.2f}시간 후")

    await asyncio.sleep(wait_seconds)


async def automatic_check():

    await client.wait_until_ready()

    while not client.is_closed():

        try:
            _, new_contests = await asyncio.to_thread(fetch_contests)

            if new_contests:

                channel = get_alert_channel(CONTEST_CHANNEL_KEY)

                if channel is not None:
                    await send_contest_embeds(
                        channel.send,
                        f"🆕 **새로운 공모전이 등록되었습니다!** ({len(new_contests)}개)",
                        new_contests
                    )

                    log.info(
                        f"새로운 공모전 {len(new_contests)}개 발견"
                    )

                else:
                    log.warning("공모전 알림 채널을 찾을 수 없습니다. /공모전설정으로 채널을 지정하세요.")

            else:
                log.info("새로운 공모전이 없습니다.")

        except Exception:

            log.exception("자동 공모전 확인 오류")

        await sleep_until_next(RUN_HOURS, "다음 자동 검사")


async def send_today_menu():
    """
    오늘 식단을 식단 알림 채널에 보낸다.
    식단 사이트 접속에 실패하면 MENU_RETRY_DELAY초 간격으로 몇 번 더 시도한다.
    """

    today = datetime.now(KST).date()

    for attempt in range(1, MENU_RETRY_COUNT + 1):
        try:
            menu = await asyncio.to_thread(dorm_menu.get_menu, today)
            break
        except Exception:
            log.exception(f"자동 식단 조회 오류 ({attempt}/{MENU_RETRY_COUNT})")
            if attempt == MENU_RETRY_COUNT:
                return
            await asyncio.sleep(MENU_RETRY_DELAY)

    channel = get_alert_channel(MENU_CHANNEL_KEY)

    if channel is None:
        log.warning("식단 알림 채널을 찾을 수 없습니다. /식단설정으로 채널을 지정하세요.")
        return

    await channel.send(embed=make_day_menu_embed(today, menu))
    log.info("오늘의 식단 전송 완료")


async def send_today_weather():
    """
    /위치설정으로 정한 지역의 오늘 날씨를 날씨 알림 채널에 보낸다.
    날씨 채널을 정하지 않았으면 식단 알림 채널로 보낸다.
    """

    code = get_setting(WEATHER_LOCATION_KEY)

    if not code:
        log.warning("날씨 위치가 설정되지 않았습니다. /위치설정으로 위치를 지정하세요.")
        return

    # 지역 이름은 목록에서 찾고, 목록을 못 받았으면 코드만 이름 대신 사용
    zone = {"code": code, "name": None}

    for attempt in range(1, MENU_RETRY_COUNT + 1):
        try:
            zone["name"] = await asyncio.to_thread(weather.zone_name, code) or code
            embed = await build_weather_embed(zone)
            break
        except Exception:
            log.exception(f"자동 날씨 조회 오류 ({attempt}/{MENU_RETRY_COUNT})")
            if attempt == MENU_RETRY_COUNT:
                return
            await asyncio.sleep(MENU_RETRY_DELAY)

    if embed is None:
        log.warning(f"{zone['name']} 오늘 예보가 없어 날씨를 보내지 않습니다.")
        return

    channel = get_alert_channel(
        WEATHER_CHANNEL_KEY if get_setting(WEATHER_CHANNEL_KEY) else MENU_CHANNEL_KEY
    )

    if channel is None:
        log.warning("날씨 알림 채널을 찾을 수 없습니다. /날씨설정으로 채널을 지정하세요.")
        return

    await channel.send(embed=embed)
    log.info("오늘의 날씨 전송 완료")


async def automatic_menu():

    await client.wait_until_ready()

    while not client.is_closed():

        # 공모전 검사와 달리 봇 시작 직후에는 보내지 않고 다음 MENU_HOURS까지 대기
        await sleep_until_next(MENU_HOURS, "다음 식단 알림")

        try:
            await send_today_menu()
        except Exception:
            log.exception("자동 식단 알림 오류")

        # 식단 전송이 실패해도 날씨는 따로 보냄
        try:
            await send_today_weather()
        except Exception:
            log.exception("자동 날씨 알림 오류")


async def main():

    init_db()

    async with client:

        await client.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
