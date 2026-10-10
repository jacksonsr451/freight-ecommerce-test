import csv
import io
import re
import zipfile
from dataclasses import dataclass
from hashlib import sha256
from pathlib import PurePosixPath

MAX_FILE_BYTES = 29_999_104  # 29,296 KiB HTTP cap; also below the 30,000,000-byte reader cap.
MAX_XLSX_ENTRIES = 500
MAX_XLSX_EXPANDED_BYTES = 300_000_000
MAX_CSV_ROWS = 1_048_576
MAX_SHIPMENTS = 200_000
OFFICIAL_COLUMN_COUNT = 28
MIME_CSV = {"text/csv", "application/csv", "application/vnd.ms-excel"}
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
UF_VALUES = {
    "AC",
    "AL",
    "AP",
    "AM",
    "BA",
    "CE",
    "DF",
    "ES",
    "GO",
    "MA",
    "MT",
    "MS",
    "MG",
    "PA",
    "PB",
    "PR",
    "PE",
    "PI",
    "RJ",
    "RN",
    "RS",
    "RO",
    "RR",
    "SC",
    "SP",
    "SE",
    "TO",
}


class ImportFileError(ValueError):
    def __init__(
        self, code: str, message: str, *, row: int | None = None, field: str | None = None
    ):
        self.code = code
        self.row = row
        self.field = field
        super().__init__(message)


@dataclass(frozen=True)
class ValidatedImportFile:
    filename: str
    content_type: str
    content: bytes
    content_sha256: str
    shipment_count: int


def _valid_cpf_cnpj(value: str) -> bool:
    digits = re.sub(r"\D", "", value)
    if len(digits) not in {11, 14} or len(set(digits)) == 1:
        return False
    if len(digits) == 11:
        first_weights, second_weights = range(10, 1, -1), range(11, 1, -1)
    else:
        first_weights = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
        second_weights = (6, *first_weights)
    first = (
        sum(int(digit) * weight for digit, weight in zip(digits[:-2], first_weights, strict=True))
        * 10
    ) % 11
    first = 0 if first == 10 else first
    second = (
        sum(int(digit) * weight for digit, weight in zip(digits[:-1], second_weights, strict=True))
        * 10
    ) % 11
    second = 0 if second == 10 else second
    return digits[-2:] == f"{first}{second}"


def _valid_nfe_key(value: str) -> bool:
    if not re.fullmatch(r"[0-9]{44}", value):
        return False
    total = 0
    weight = 2
    for digit in reversed(value[:43]):
        total += int(digit) * weight
        weight = 2 if weight == 9 else weight + 1
    remainder = total % 11
    expected = 0 if remainder in {0, 1} else 11 - remainder
    return int(value[-1]) == expected


def _validate_csv(content: bytes) -> int:
    if content.count(b"\n") + (not content.endswith(b"\n")) > MAX_CSV_ROWS:
        raise ImportFileError("file_row_limit", "CSV excede o limite estrutural de linhas.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = content.decode("cp1252")
        except UnicodeDecodeError:
            raise ImportFileError(
                "file_encoding_invalid", "CSV deve usar UTF-8 ou Windows-1252."
            ) from None
    first_end = text.find("\n")
    if first_end >= 0:
        second_start = first_end + 1
        second_end = text.find("\n", second_start)
        sample = text[
            second_start : second_end if second_end >= 0 else second_start + 16_384
        ].rstrip("\r")
    else:
        sample = ""
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;")
    except csv.Error:
        raise ImportFileError(
            "file_delimiter_invalid", "Não foi possível identificar separador CSV."
        ) from None
    if dialect.delimiter not in {",", ";"}:
        raise ImportFileError(
            "file_delimiter_invalid", "CSV aceita separador vírgula ou ponto e vírgula."
        )
    try:
        rows = csv.reader(io.StringIO(text, newline=""), dialect=dialect, strict=True)
        instruction = next(rows, None)
        header = next(rows, None)
        if not instruction or not any(cell.strip() for cell in instruction):
            raise ImportFileError(
                "file_instruction_missing", "CSV precisa da linha de instruções na linha 1."
            )
        if header is None or len(header) != OFFICIAL_COLUMN_COUNT:
            raise ImportFileError(
                "file_header_width_invalid", "O cabeçalho oficial atual precisa ter 28 colunas."
            )
        if not any(cell.strip() for cell in header):
            raise ImportFileError("file_header_missing", "Cabeçalho ausente na linha 2.")
        if any(len(cell) > 180 for cell in header):
            raise ImportFileError(
                "file_field_length", "Cabeçalho contém campo acima de 180 caracteres.", row=2
            )
        count = 0
        for row_number, row in enumerate(rows, start=3):
            if not row or not any(cell.strip() for cell in row):
                continue
            if len(row) > 64:
                raise ImportFileError(
                    "file_cell_limit", "Linha CSV excede 64 células.", row=row_number
                )
            if len(row) != OFFICIAL_COLUMN_COUNT:
                raise ImportFileError(
                    "file_row_width_invalid", "Linha precisa ter 28 colunas.", row=row_number
                )
            if any(len(cell) > 180 for cell in row):
                raise ImportFileError(
                    "file_field_length", "Campo excede 180 caracteres.", row=row_number
                )
            if any(any(ord(char) < 32 and char not in "\t" for char in cell) for cell in row):
                raise ImportFileError(
                    "file_control_character", "Campo contém caractere de controle.", row=row_number
                )
            _validate_csv_row(row, row_number)
            count += 1
            if count > MAX_SHIPMENTS:
                raise ImportFileError("file_shipment_limit", "Arquivo excede 200.000 envios.")
        if count == 0:
            raise ImportFileError(
                "file_rows_missing", "Inclua ao menos uma linha de envio a partir da linha 3."
            )
        return count
    except csv.Error:
        raise ImportFileError("file_csv_invalid", "CSV malformado.") from None


def _validate_csv_row(row: list[str], row_number: int) -> None:
    # Column positions follow the semantic order in the reference. Literal header labels
    # are deliberately not matched because the reference does not publish their spelling.
    required_checks = (
        (0, "invoice_number"),
        (1, "nfe_access_key"),
        (3, "recipient_document"),
        (4, "recipient_phone"),
        (17, "sender_document"),
    )
    for index, field in required_checks:
        if not row[index].strip():
            raise ImportFileError(
                "fiscal_field_missing",
                "Campo fiscal/identificação obrigatório ausente.",
                row=row_number,
                field=field,
            )
    if not re.fullmatch(r"[1-9][0-9]{0,8}", row[0].strip()):
        raise ImportFileError(
            "invoice_number_invalid",
            "Número da nota fora do formato documentado.",
            row=row_number,
            field="invoice_number",
        )
    if not _valid_nfe_key(row[1].strip()):
        raise ImportFileError(
            "nfe_key_invalid",
            "Chave NF-e inválida (44 dígitos e verificador).",
            row=row_number,
            field="nfe_access_key",
        )
    for index, field in ((3, "recipient_document"), (17, "sender_document")):
        if not _valid_cpf_cnpj(row[index]):
            raise ImportFileError(
                "document_invalid", "CPF/CNPJ inválido.", row=row_number, field=field
            )
    if (
        not re.fullmatch(r"\+?[0-9() -]{8,22}", row[4].strip())
        or len(re.sub(r"\D", "", row[4])) < 10
    ):
        raise ImportFileError(
            "recipient_phone_invalid",
            "Telefone do destinatário precisa conter DDD.",
            row=row_number,
            field="recipient_phone",
        )
    if not re.fullmatch(r"[0-9]{8}", row[5].strip()) or not re.fullmatch(
        r"[0-9]{8}", row[18].strip()
    ):
        raise ImportFileError(
            "postal_code_invalid",
            "CEP de origem/destino deve ter 8 dígitos.",
            row=row_number,
            field="postal_code",
        )
    if row[11].strip().upper() not in UF_VALUES or row[24].strip().upper() not in UF_VALUES:
        raise ImportFileError(
            "state_invalid", "UF de origem/destino inválida.", row=row_number, field="state"
        )


def _validate_xlsx(content: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = archive.infolist()
            if len(members) > MAX_XLSX_ENTRIES:
                raise ImportFileError("xlsx_entry_limit", "XLSX excede 500 entradas ZIP.")
            if sum(member.file_size for member in members) > MAX_XLSX_EXPANDED_BYTES:
                raise ImportFileError(
                    "xlsx_expanded_limit", "XLSX excede 300.000.000 bytes descompactados."
                )
            names = {member.filename for member in members}
            if "xl/workbook.xml" not in names or not any(
                name.startswith("xl/worksheets/") and name.endswith(".xml") for name in names
            ):
                raise ImportFileError(
                    "xlsx_structure_invalid", "XLSX não contém uma primeira planilha legível."
                )
    except ImportFileError:
        raise
    except (zipfile.BadZipFile, OSError, ValueError):
        raise ImportFileError("xlsx_invalid", "Arquivo XLSX inválido.") from None


def validate_import_file(
    filename: str | None, content_type: str | None, content: bytes
) -> ValidatedImportFile:
    if not filename:
        raise ImportFileError("filename_missing", "Selecione um arquivo CSV ou XLSX.")
    basename = PurePosixPath(filename.replace("\\", "/")).name
    if not basename or len(basename) > 255 or any(ord(char) < 32 for char in basename):
        raise ImportFileError("filename_invalid", "Nome de arquivo inválido.")
    if not content or len(content) > MAX_FILE_BYTES:
        raise ImportFileError(
            "file_size_invalid", "Arquivo vazio ou acima do limite de 29.296 KiB."
        )
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    suffix = basename.rsplit(".", 1)[-1].lower() if "." in basename else ""
    if suffix == "csv" and media_type in MIME_CSV:
        count = _validate_csv(content)
    elif suffix == "xlsx" and media_type == MIME_XLSX:
        _validate_xlsx(content)
        # XLSX contents are validated by the documented external workbook reader; no local
        # dependency is installed to parse cells, so no local fiscal assertion is fabricated.
        count = 0
    else:
        raise ImportFileError("file_type_invalid", "Use CSV/text-csv ou XLSX com MIME compatível.")
    return ValidatedImportFile(
        filename=basename,
        content_type=media_type,
        content=content,
        content_sha256=sha256(content).hexdigest(),
        shipment_count=count,
    )
