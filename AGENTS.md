# Agent Development Guidelines

## Build & Test Commands
- **Python (lagasafn-xml)**: `./lagasafn-xml` (main script), `pip install -r requirements.txt`
- **Django API (codex-api)**: `python manage.py runserver`, `python manage.py test [app_name]`, single test: `python manage.py test app.tests.TestClass.test_method`
- **Frontend (codex-ui)**: `npm run dev` (development), `npm run build` (production), `npm run lint`, `npm run lint:fix`
- **Format Python**: `black .` (install via `pip install black`)

## Code Style - Python
- **Imports**: Standard library first, then third-party, then local (from lagasafn.* imports)
- **Classes**: CamelCase (e.g., `LawParser`, `SearchEngine`)
- **Functions/Variables**: snake_case (e.g., `get_law_links`, `law_num`)
- **Constants**: UPPER_SNAKE_CASE (e.g., `CURRENT_PARLIAMENT_VERSION`)
- **Type hints**: Not enforced but encouraged for new code
- **Error handling**: Use custom exceptions from `lagasafn.exceptions`

## Code Style - TypeScript/JSX (codex-ui)
- **Formatting**: 4-space indentation, single quotes, semicolons required
- **Variables**: camelCase (no leading/trailing underscores)
- **Components**: PascalCase for components and functions
- **ESLint**: Strict TypeScript rules, run `npm run lint` before commits

## Project Structure Notes
- **data/patches/**: Contains HTML patches for fixing parsing errors in specific law versions
- **data/xml/**: Generated XML files organized by parliament version (e.g., 155/)