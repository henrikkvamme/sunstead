import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/qr")({
  component: QrPage,
});

const QR_TARGET = "http://sunsteadgoblins.com/";
const QR_VERSION = 2;
const QR_SIZE = QR_VERSION * 4 + 17;
const QR_DATA_CODEWORDS = 34;
const QR_ERROR_CODEWORDS = 10;
const QR_QUIET_ZONE = 4;
const QR_EC_LEVEL_LOW = 1;

function QrPage() {
  const matrix = createQrMatrix(QR_TARGET);
  const activeCells = matrix.flatMap((row, y) =>
    row.flatMap((isActive, x) => (isActive ? [{ id: `${x}-${y}`, x, y }] : [])),
  );
  const viewBoxSize = QR_SIZE + QR_QUIET_ZONE * 2;

  return (
    <main className="medicine-graph-screen qr-page" aria-label="Sunstead QR code">
      <section className="qr-minimal" aria-label={`QR code linking to ${QR_TARGET}`}>
        <div className="qr-brand" aria-label="Sunstead">
          <img
            alt=""
            aria-hidden
            className="sanitas-logo-mark"
            src="/logo-candidates/sanitas-logo-5-compact-bottle-transparent.png"
          />
          <span>Sunstead</span>
        </div>

        <svg
          className="qr-svg"
          role="img"
          viewBox={`0 0 ${viewBoxSize} ${viewBoxSize}`}
          aria-label={`QR code for ${QR_TARGET}`}
          shapeRendering="crispEdges"
        >
          <rect className="qr-svg-field" width={viewBoxSize} height={viewBoxSize} rx="2" />
          <g transform={`translate(${QR_QUIET_ZONE} ${QR_QUIET_ZONE})`}>
            {activeCells.map((cell) => (
              <rect
                className="qr-svg-cell"
                height="1"
                key={cell.id}
                width="1"
                x={cell.x}
                y={cell.y}
              />
            ))}
          </g>
        </svg>

        <a className="qr-dashboard-link" href="/">
          Open dashboard
        </a>
      </section>
    </main>
  );
}

function createQrMatrix(content: string) {
  const dataCodewords = encodeQrData(content);
  const errorCodewords = computeErrorCodewords(dataCodewords, QR_ERROR_CODEWORDS);
  const allCodewords = [...dataCodewords, ...errorCodewords];
  const { modules: functionModules, reserved } = createFunctionModules();
  const rawModules = functionModules.map((row) => [...row]);
  placeDataBits(rawModules, reserved, codewordsToBits(allCodewords));

  let bestMatrix = rawModules;
  let bestScore = Number.POSITIVE_INFINITY;

  for (let mask = 0; mask < 8; mask += 1) {
    const candidate = rawModules.map((row) => [...row]);
    applyMask(candidate, reserved, mask);
    drawFormatBits(candidate, mask);

    const score = scoreMatrix(candidate);
    if (score < bestScore) {
      bestMatrix = candidate;
      bestScore = score;
    }
  }

  return bestMatrix;
}

function encodeQrData(content: string) {
  const bits: number[] = [];
  const bytes = [...new TextEncoder().encode(content)];
  appendBits(bits, 0b0100, 4);
  appendBits(bits, bytes.length, 8);

  for (const byte of bytes) {
    appendBits(bits, byte, 8);
  }

  const dataBitCapacity = QR_DATA_CODEWORDS * 8;
  appendBits(bits, 0, Math.min(4, dataBitCapacity - bits.length));

  while (bits.length % 8 !== 0) {
    bits.push(0);
  }

  const codewords: number[] = [];
  for (let index = 0; index < bits.length; index += 8) {
    codewords.push(bitsToByte(bits.slice(index, index + 8)));
  }

  for (let padIndex = 0; codewords.length < QR_DATA_CODEWORDS; padIndex += 1) {
    codewords.push(padIndex % 2 === 0 ? 0xec : 0x11);
  }

  return codewords;
}

function appendBits(bits: number[], value: number, length: number) {
  for (let index = length - 1; index >= 0; index -= 1) {
    bits.push((value >>> index) & 1);
  }
}

function bitsToByte(bits: number[]) {
  return bits.reduce((byte, bit) => (byte << 1) | bit, 0);
}

function codewordsToBits(codewords: number[]) {
  return codewords.flatMap((codeword) =>
    Array.from({ length: 8 }, (_, index) => (codeword >>> (7 - index)) & 1),
  );
}

function computeErrorCodewords(data: number[], degree: number) {
  const divisor = computeReedSolomonDivisor(degree);
  const remainder = Array.from({ length: degree }, () => 0);

  for (const codeword of data) {
    const factor = codeword ^ (remainder.shift() ?? 0);
    remainder.push(0);

    for (let index = 0; index < divisor.length; index += 1) {
      remainder[index] ^= multiplyGalois(divisor[index], factor);
    }
  }

  return remainder;
}

function computeReedSolomonDivisor(degree: number) {
  const result = Array.from({ length: degree }, () => 0);
  result[degree - 1] = 1;

  let root = 1;
  for (let index = 0; index < degree; index += 1) {
    for (let coefficient = 0; coefficient < result.length; coefficient += 1) {
      result[coefficient] = multiplyGalois(result[coefficient], root);
      if (coefficient + 1 < result.length) {
        result[coefficient] ^= result[coefficient + 1];
      }
    }

    root = multiplyGalois(root, 0x02);
  }

  return result;
}

function multiplyGalois(left: number, right: number) {
  let product = 0;

  for (let bit = 7; bit >= 0; bit -= 1) {
    product = (product << 1) ^ ((product >>> 7) * 0x11d);
    product ^= ((right >>> bit) & 1) * left;
  }

  return product & 0xff;
}

function createFunctionModules() {
  const modules = createMatrix(false);
  const reserved = createMatrix(false);

  const setFunctionModule = (x: number, y: number, isDark: boolean) => {
    modules[y][x] = isDark;
    reserved[y][x] = true;
  };

  drawFinderPattern(setFunctionModule, 0, 0);
  drawFinderPattern(setFunctionModule, QR_SIZE - 7, 0);
  drawFinderPattern(setFunctionModule, 0, QR_SIZE - 7);
  drawAlignmentPattern(setFunctionModule, 18, 18);

  for (let index = 0; index < QR_SIZE; index += 1) {
    if (!reserved[6][index]) {
      setFunctionModule(index, 6, index % 2 === 0);
    }

    if (!reserved[index][6]) {
      setFunctionModule(6, index, index % 2 === 0);
    }
  }

  setFunctionModule(8, QR_SIZE - 8, true);
  reserveFormatAreas(reserved);

  return { modules, reserved };
}

function createMatrix(value: boolean) {
  return Array.from({ length: QR_SIZE }, () => Array.from({ length: QR_SIZE }, () => value));
}

function drawFinderPattern(
  setFunctionModule: (x: number, y: number, isDark: boolean) => void,
  left: number,
  top: number,
) {
  for (let y = -1; y <= 7; y += 1) {
    for (let x = -1; x <= 7; x += 1) {
      const moduleX = left + x;
      const moduleY = top + y;

      if (moduleX < 0 || moduleY < 0 || moduleX >= QR_SIZE || moduleY >= QR_SIZE) {
        continue;
      }

      const isDark =
        x >= 0 &&
        x <= 6 &&
        y >= 0 &&
        y <= 6 &&
        (x === 0 || x === 6 || y === 0 || y === 6 || (x >= 2 && x <= 4 && y >= 2 && y <= 4));

      setFunctionModule(moduleX, moduleY, isDark);
    }
  }
}

function drawAlignmentPattern(
  setFunctionModule: (x: number, y: number, isDark: boolean) => void,
  centerX: number,
  centerY: number,
) {
  for (let y = -2; y <= 2; y += 1) {
    for (let x = -2; x <= 2; x += 1) {
      const distance = Math.max(Math.abs(x), Math.abs(y));
      setFunctionModule(centerX + x, centerY + y, distance === 2 || distance === 0);
    }
  }
}

function reserveFormatAreas(reserved: boolean[][]) {
  for (let index = 0; index < 9; index += 1) {
    if (index !== 6) {
      reserved[8][index] = true;
      reserved[index][8] = true;
    }
  }

  for (let index = QR_SIZE - 8; index < QR_SIZE; index += 1) {
    reserved[8][index] = true;
    reserved[index][8] = true;
  }
}

function placeDataBits(modules: boolean[][], reserved: boolean[][], bits: number[]) {
  let bitIndex = 0;
  let upward = true;

  for (let right = QR_SIZE - 1; right > 0; right -= 2) {
    if (right === 6) {
      right -= 1;
    }

    for (let rowOffset = 0; rowOffset < QR_SIZE; rowOffset += 1) {
      const y = upward ? QR_SIZE - 1 - rowOffset : rowOffset;

      for (let x = right; x >= right - 1; x -= 1) {
        if (reserved[y][x]) {
          continue;
        }

        modules[y][x] = bits[bitIndex] === 1;
        bitIndex += 1;
      }
    }

    upward = !upward;
  }
}

function applyMask(modules: boolean[][], reserved: boolean[][], mask: number) {
  for (let y = 0; y < QR_SIZE; y += 1) {
    for (let x = 0; x < QR_SIZE; x += 1) {
      if (!reserved[y][x] && maskApplies(mask, x, y)) {
        modules[y][x] = !modules[y][x];
      }
    }
  }
}

function maskApplies(mask: number, x: number, y: number) {
  switch (mask) {
    case 0:
      return (x + y) % 2 === 0;
    case 1:
      return y % 2 === 0;
    case 2:
      return x % 3 === 0;
    case 3:
      return (x + y) % 3 === 0;
    case 4:
      return (Math.floor(y / 2) + Math.floor(x / 3)) % 2 === 0;
    case 5:
      return ((x * y) % 2) + ((x * y) % 3) === 0;
    case 6:
      return (((x * y) % 2) + ((x * y) % 3)) % 2 === 0;
    case 7:
      return (((x + y) % 2) + ((x * y) % 3)) % 2 === 0;
    default:
      return false;
  }
}

function drawFormatBits(modules: boolean[][], mask: number) {
  const bits = computeFormatBits(mask);
  const set = (x: number, y: number, bitIndex: number) => {
    modules[y][x] = ((bits >>> bitIndex) & 1) !== 0;
  };

  for (let index = 0; index <= 5; index += 1) {
    set(8, index, index);
  }

  set(8, 7, 6);
  set(8, 8, 7);
  set(7, 8, 8);

  for (let index = 9; index < 15; index += 1) {
    set(14 - index, 8, index);
  }

  for (let index = 0; index < 8; index += 1) {
    set(QR_SIZE - 1 - index, 8, index);
  }

  for (let index = 8; index < 15; index += 1) {
    set(8, QR_SIZE - 15 + index, index);
  }

  modules[QR_SIZE - 8][8] = true;
}

function computeFormatBits(mask: number) {
  const data = (QR_EC_LEVEL_LOW << 3) | mask;
  let remainder = data << 10;

  for (let shift = bitLength(remainder) - 11; shift >= 0; shift -= 1) {
    remainder ^= 0x537 << shift;
  }

  return ((data << 10) | remainder) ^ 0x5412;
}

function bitLength(value: number) {
  let length = 0;

  while (value !== 0) {
    length += 1;
    value >>>= 1;
  }

  return length;
}

function scoreMatrix(matrix: boolean[][]) {
  return (
    scoreRuns(matrix) +
    scoreRuns(rotateMatrix(matrix)) +
    scoreBlocks(matrix) +
    scoreFinderLikePatterns(matrix) +
    scoreDarkBalance(matrix)
  );
}

function scoreRuns(matrix: boolean[][]) {
  let score = 0;

  for (const row of matrix) {
    let runColor = row[0];
    let runLength = 1;

    for (let index = 1; index < row.length; index += 1) {
      if (row[index] === runColor) {
        runLength += 1;
        continue;
      }

      if (runLength >= 5) {
        score += 3 + (runLength - 5);
      }

      runColor = row[index];
      runLength = 1;
    }

    if (runLength >= 5) {
      score += 3 + (runLength - 5);
    }
  }

  return score;
}

function scoreBlocks(matrix: boolean[][]) {
  let score = 0;

  for (let y = 0; y < QR_SIZE - 1; y += 1) {
    for (let x = 0; x < QR_SIZE - 1; x += 1) {
      const color = matrix[y][x];
      if (
        matrix[y][x + 1] === color &&
        matrix[y + 1][x] === color &&
        matrix[y + 1][x + 1] === color
      ) {
        score += 3;
      }
    }
  }

  return score;
}

function scoreFinderLikePatterns(matrix: boolean[][]) {
  const pattern = [true, false, true, true, true, false, true, false, false, false, false];
  let score = 0;

  const scoreRows = (rows: boolean[][]) => {
    for (const row of rows) {
      for (let index = 0; index <= row.length - pattern.length; index += 1) {
        const matches = pattern.every((value, offset) => row[index + offset] === value);
        const reverseMatches = pattern.every(
          (value, offset) => row[index + pattern.length - 1 - offset] === value,
        );

        if (matches || reverseMatches) {
          score += 40;
        }
      }
    }
  };

  scoreRows(matrix);
  scoreRows(rotateMatrix(matrix));

  return score;
}

function scoreDarkBalance(matrix: boolean[][]) {
  const darkModules = matrix.flat().filter(Boolean).length;
  const totalModules = QR_SIZE * QR_SIZE;
  const darkPercent = (darkModules * 100) / totalModules;

  return Math.floor(Math.abs(darkPercent - 50) / 5) * 10;
}

function rotateMatrix(matrix: boolean[][]) {
  return Array.from({ length: QR_SIZE }, (_, y) =>
    Array.from({ length: QR_SIZE }, (_, x) => matrix[x][y]),
  );
}
