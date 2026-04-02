"""Seed data for testing and development."""

from datetime import date

from loom.storage import (
    Bullet,
    BulletType,
    Confidence,
    Education,
    Experience,
    InMemoryDataStorage,
    Profile,
    Project,
    Skill,
    SkillLevel,
)


async def seed_sample_profile(storage: InMemoryDataStorage) -> Profile:
    """Create a sample profile with full data for testing.

    Returns:
        The created Profile
    """
    # Create profile
    profile = Profile(
        name_en="Alex Chen",
        name_zh="陈亚历",
        email="alex.chen@example.com",
        phone="+1-555-0123",
        location_en="San Francisco, CA",
        location_zh="旧金山, 加州",
        summary_en="Senior backend engineer with 6+ years of experience building "
                   "scalable distributed systems. Passionate about clean architecture "
                   "and developer experience.",
        summary_zh=None,
    )
    await storage.save_profile(profile)

    # Add skills
    skills_data = [
        ("Python", SkillLevel.EXPERT, "Primary language for backend services"),
        ("Go", SkillLevel.PROFICIENT, "High-performance microservices"),
        ("PostgreSQL", SkillLevel.EXPERT, "Primary database, query optimization"),
        ("Redis", SkillLevel.PROFICIENT, "Caching and session management"),
        ("Kubernetes", SkillLevel.PROFICIENT, "Container orchestration"),
        ("Docker", SkillLevel.EXPERT, "Containerization"),
        ("AWS", SkillLevel.PROFICIENT, "EC2, S3, Lambda, RDS"),
        ("Kafka", SkillLevel.FAMILIAR, "Event streaming"),
    ]
    for name, level, context_en in skills_data:
        await storage.save_skill(Skill(
            profile_id=profile.id,
            name=name,
            level=level,
            context_en=context_en,
        ))

    # Add experience 1 (current)
    exp1 = Experience(
        profile_id=profile.id,
        company_en="TechScale Inc.",
        title_en="Senior Software Engineer",
        location_en="San Francisco, CA",
        start_date=date(2021, 3, 1),
        end_date=None,
    )
    await storage.save_experience(exp1)

    # Bullets for exp1
    bullets_exp1 = [
        (BulletType.BUSINESS_IMPACT, 1,
         "Led migration of monolithic API to microservices architecture, "
         "reducing deployment time from 2 hours to 15 minutes",
         {"situation": "Legacy monolith causing slow deployments",
          "action": "Designed and implemented microservices architecture",
          "result_quantified": "87% reduction in deployment time"},
         [{"name": "Python", "role": "primary"}, {"name": "Kubernetes", "role": "orchestration"}],
         ["microservices", "architecture", "deployment"]),

        (BulletType.SCALE, 2,
         "Optimized database queries and implemented caching layer, "
         "achieving 40% latency reduction for API endpoints serving 10M daily requests",
         {"situation": "High latency on critical API endpoints",
          "action": "Query optimization and Redis caching",
          "result_quantified": "40% latency reduction, 10M daily requests"},
         [{"name": "PostgreSQL", "role": "primary"}, {"name": "Redis", "role": "caching"}],
         ["performance", "optimization", "scale"]),

        (BulletType.TECHNICAL_DESIGN, 2,
         "Designed event-driven architecture using Kafka for real-time data processing pipeline",
         {"situation": "Need for real-time data processing",
          "action": "Implemented event-driven architecture with Kafka",
          "result_quantified": "Processing 500K events/second"},
         [{"name": "Kafka", "role": "messaging"}, {"name": "Python", "role": "consumers"}],
         ["event-driven", "real-time", "data pipeline"]),

        (BulletType.COLLABORATION, 3,
         "Mentored 3 junior engineers, established code review practices and documentation standards",
         {"situation": "Growing team needed better practices",
          "action": "Established mentorship and code review processes",
          "result_qualitative": "Improved team velocity and code quality"},
         [],
         ["mentoring", "leadership", "team"]),
    ]

    for btype, priority, raw, star, tech, keywords in bullets_exp1:
        await storage.save_bullet(Bullet(
            experience_id=exp1.id,
            type=btype,
            priority=priority,
            content_en=raw,
            raw_text=raw,
            star_data=star,
            tech_stack=tech,
            jd_keywords=keywords,
            confidence=Confidence.HIGH,
        ))

    # Add experience 2 (previous)
    exp2 = Experience(
        profile_id=profile.id,
        company_en="DataFlow Systems",
        title_en="Software Engineer",
        location_en="Seattle, WA",
        start_date=date(2018, 6, 1),
        end_date=date(2021, 2, 28),
    )
    await storage.save_experience(exp2)

    # Bullets for exp2
    bullets_exp2 = [
        (BulletType.BUSINESS_IMPACT, 2,
         "Built automated data pipeline processing 5M records daily, "
         "reducing manual data processing time by 90%",
         {"situation": "Manual data processing was time-consuming",
          "action": "Built automated ETL pipeline",
          "result_quantified": "5M records/day, 90% time reduction"},
         [{"name": "Python", "role": "ETL"}, {"name": "AWS", "role": "infrastructure"}],
         ["data pipeline", "automation", "ETL"]),

        (BulletType.IMPLEMENTATION, 2,
         "Developed RESTful APIs using FastAPI with comprehensive test coverage (95%)",
         {"situation": "Need for new API endpoints",
          "action": "Implemented APIs with FastAPI and pytest",
          "result_quantified": "95% test coverage"},
         [{"name": "Python", "role": "primary"}, {"name": "FastAPI", "role": "framework"}],
         ["API", "REST", "testing"]),

        (BulletType.PROBLEM_SOLVING, 3,
         "Identified and resolved memory leak causing production outages, "
         "achieving 99.9% uptime",
         {"situation": "Recurring production outages",
          "action": "Root cause analysis and fix",
          "result_quantified": "99.9% uptime achieved"},
         [{"name": "Python", "role": "debugging"}],
         ["debugging", "reliability", "production"]),
    ]

    for btype, priority, raw, star, tech, keywords in bullets_exp2:
        await storage.save_bullet(Bullet(
            experience_id=exp2.id,
            type=btype,
            priority=priority,
            content_en=raw,
            raw_text=raw,
            star_data=star,
            tech_stack=tech,
            jd_keywords=keywords,
            confidence=Confidence.HIGH,
        ))

    # Add education
    await storage.save_education(Education(
        profile_id=profile.id,
        institution_en="University of California, Berkeley",
        degree_en="B.S.",
        field_en="Computer Science",
        start_date=date(2014, 8, 1),
        end_date=date(2018, 5, 15),
    ))

    # Add project
    await storage.save_project(Project(
        profile_id=profile.id,
        name_en="Open Source CLI Tool",
        description_en="Command-line tool for API testing with 500+ GitHub stars",
        role_en="Creator & Maintainer",
        tech_stack=[{"name": "Go"}, {"name": "Docker"}],
        bullets=[
            {"text": "Built CLI tool for API testing used by 1000+ developers"},
            {"text": "Implemented plugin system for extensibility"},
        ],
    ))

    return profile
